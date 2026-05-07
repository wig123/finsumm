#!/usr/bin/env python3
"""
Qwen3-VL-30B-A3B API 推理脚本
使用阿里云 DashScope OpenAI 兼容接口
支持双语提示词，与本地推理参数保持一致
"""
import os
import json
import base64
import time
import argparse
import io
from pathlib import Path
from tqdm import tqdm
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from PIL import Image

# API 配置
API_KEY = "<YOUR_API_KEY>"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3-vl-30b-a3b-instruct"

# 像素限制 - 与本地推理保持一致
PIXEL_LIMITS = {
    "max_pixels": 1280 * 32 * 32,  # ~1,310,720 pixels
    "min_pixels": 256 * 32 * 32,   # ~262,144 pixels
}

# 线程安全的计数器
lock = threading.Lock()
success_count = 0
failed_count = 0


def resize_image_if_needed(image_path: str) -> Image.Image:
    """
    根据像素限制调整图片大小，与本地推理保持一致
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    pixels = w * h

    max_pixels = PIXEL_LIMITS["max_pixels"]
    min_pixels = PIXEL_LIMITS["min_pixels"]

    # 如果超过最大像素限制，缩小图片
    if pixels > max_pixels:
        ratio = (max_pixels / pixels) ** 0.5
        new_w, new_h = int(w * ratio), int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    # 如果低于最小像素限制，放大图片
    elif pixels < min_pixels:
        ratio = (min_pixels / pixels) ** 0.5
        new_w, new_h = int(w * ratio), int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img


def encode_image_to_base64(image_path: str) -> str:
    """将本地图片编码为 base64，应用像素限制"""
    img = resize_image_if_needed(image_path)

    # 将 PIL Image 编码为 base64
    buffer = io.BytesIO()
    # 根据原始格式保存
    ext = Path(image_path).suffix.lower()
    if ext in [".png"]:
        img.save(buffer, format="PNG")
    else:
        img.save(buffer, format="JPEG", quality=95)

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """根据文件扩展名获取 MIME 类型"""
    ext = Path(image_path).suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_types.get(ext, "image/jpeg")


def inference_single(
    client: OpenAI,
    sample: dict,
    prompt_cn: str,
    prompt_en: str,
    max_retries: int = 3
) -> dict:
    """单个样本推理"""
    global success_count, failed_count

    sample_id = sample["id"]
    image_path = sample["image_path"]
    source = sample.get("source", "")

    # 根据来源选择提示词
    if source == "sync_300_cn":
        prompt_text = prompt_cn
        prompt_lang = "zh"
    else:
        prompt_text = prompt_en
        prompt_lang = "en"

    for attempt in range(max_retries):
        try:
            # 编码图片为 base64
            image_base64 = encode_image_to_base64(image_path)
            mime_type = get_image_mime_type(image_path)
            image_url = f"data:{mime_type};base64,{image_base64}"

            start_time = time.time()

            # 调用 API - 使用贪婪解码 (temperature=0)
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url}
                            },
                            {
                                "type": "text",
                                "text": prompt_text
                            }
                        ]
                    }
                ],
                max_tokens=2048,
                temperature=0,  # 贪婪解码，与本地推理 do_sample=False 一致
            )

            inference_time = time.time() - start_time
            generated_text = response.choices[0].message.content

            with lock:
                success_count += 1

            return {
                "id": sample_id,
                "model": MODEL_NAME,
                "generated_text": generated_text,
                "ground_truth": sample.get("ground_truth", ""),
                "inference_time": inference_time,
                "image_path": image_path,
                "source": source,
                "prompt_lang": prompt_lang,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                    "completion_tokens": response.usage.completion_tokens if response.usage else None,
                    "total_tokens": response.usage.total_tokens if response.usage else None,
                }
            }

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
                continue

            with lock:
                failed_count += 1

            return {
                "id": sample_id,
                "model": MODEL_NAME,
                "error": str(e),
                "image_path": image_path,
                "source": source,
            }


def main():
    # 获取脚本所在目录作为基础路径
    script_dir = Path(__file__).parent.resolve()

    parser = argparse.ArgumentParser(description="Qwen3-VL-30B API 推理脚本")
    parser.add_argument("--dataset", type=str, default=str(script_dir / "dataset_index_1000_local.json"))
    parser.add_argument("--prompt-cn", type=str, default=str(script_dir / "prompt.txt"))
    parser.add_argument("--prompt-en", type=str, default=str(script_dir / "prompt_en.txt"))
    parser.add_argument("--output-dir", type=str, default=str(script_dir / "outputs"))
    parser.add_argument("--workers", type=int, default=4, help="并发线程数")
    parser.add_argument("--resume", action="store_true", help="从上次中断处继续")
    args = parser.parse_args()

    # 初始化客户端
    client = OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL,
    )

    # 加载数据
    with open(args.dataset) as f:
        samples = json.load(f)

    with open(args.prompt_cn) as f:
        prompt_cn = f.read().strip()

    with open(args.prompt_en) as f:
        prompt_en = f.read().strip()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"{MODEL_NAME.replace('-', '_')}_results.jsonl"

    # 断点续传
    completed_ids = set()
    if args.resume and output_file.exists():
        with open(output_file) as f:
            for line in f:
                try:
                    result = json.loads(line)
                    completed_ids.add(result["id"])
                except:
                    pass
        print(f"断点续传: 已完成 {len(completed_ids)} 个样本")

    # 过滤已完成的样本
    pending_samples = [s for s in samples if s["id"] not in completed_ids]

    # 统计来源分布
    source_counts = {}
    for s in pending_samples:
        src = s.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    print(f"\n{'='*60}")
    print(f"{MODEL_NAME} API 推理")
    print(f"{'='*60}")
    print(f"总样本数: {len(samples)}")
    print(f"待推理: {len(pending_samples)}")
    print(f"已完成: {len(completed_ids)}")
    print(f"来源分布: {source_counts}")
    print(f"并发数: {args.workers}")
    print(f"像素限制: max={PIXEL_LIMITS['max_pixels']:,}, min={PIXEL_LIMITS['min_pixels']:,}")
    print(f"输出文件: {output_file}")
    print(f"{'='*60}\n")

    if len(pending_samples) == 0:
        print("所有样本已完成!")
        return

    # 并发推理
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(inference_single, client, sample, prompt_cn, prompt_en): sample
            for sample in pending_samples
        }

        with tqdm(total=len(pending_samples), desc="推理进度") as pbar:
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

                # 实时写入文件（断点续传）
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")

                pbar.update(1)
                pbar.set_postfix({"成功": success_count, "失败": failed_count})

    # 统计结果
    success_results = [r for r in results if "error" not in r]
    failed_results = [r for r in results if "error" in r]

    # 按来源统计
    source_stats = {}
    for r in success_results:
        source = r.get("source", "unknown")
        if source not in source_stats:
            source_stats[source] = {"count": 0, "total_time": 0, "total_tokens": 0}
        source_stats[source]["count"] += 1
        source_stats[source]["total_time"] += r.get("inference_time", 0)
        if r.get("usage") and r["usage"].get("total_tokens"):
            source_stats[source]["total_tokens"] += r["usage"]["total_tokens"]

    # 保存统计
    stats = {
        "model": MODEL_NAME,
        "total_samples": len(samples),
        "success_count": len(success_results) + len(completed_ids),
        "failed_count": len(failed_results),
        "success_rate": (len(success_results) + len(completed_ids)) / len(samples) if samples else 0,
        "avg_inference_time": sum(r.get("inference_time", 0) for r in success_results) / len(success_results) if success_results else 0,
        "source_breakdown": {
            k: {
                "count": v["count"],
                "avg_time": v["total_time"] / v["count"] if v["count"] > 0 else 0,
                "avg_tokens": v["total_tokens"] / v["count"] if v["count"] > 0 else 0,
            }
            for k, v in source_stats.items()
        }
    }

    stats_file = output_dir / f"{MODEL_NAME.replace('-', '_')}_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"{MODEL_NAME} 推理完成")
    print(f"{'='*60}")
    print(f"成功: {stats['success_count']} | 失败: {stats['failed_count']}")
    print(f"成功率: {stats['success_rate']:.2%}")
    print(f"平均推理时间: {stats['avg_inference_time']:.2f}s")
    print(f"\n按来源统计:")
    for source, data in stats["source_breakdown"].items():
        print(f"  {source}: {data['count']}个, 平均{data['avg_time']:.2f}s, 平均{data['avg_tokens']:.0f}tokens")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
