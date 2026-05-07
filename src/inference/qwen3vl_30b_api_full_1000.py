#!/usr/bin/env python3
"""
Qwen3-VL-30B-A3B API 推理脚本 - 全量1000样本版本
使用阿里云 DashScope OpenAI 兼容接口
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

# 数据路径
DATA_BASE = "/data/finmme-bench/data"
OUTPUT_BASE = "/data/finmme-bench/outputs/full_1000"

# 数据集配置
DATASETS = ["fin-chart_200", "finmme_200", "sync_300_cn", "sync_300_en"]

# 像素限制 - 与本地推理保持一致
PIXEL_LIMITS = {
    "max_pixels": 1280 * 32 * 32,
    "min_pixels": 256 * 32 * 32,
}

# 线程安全的计数器
lock = threading.Lock()
success_count = 0
failed_count = 0


def get_all_samples() -> list:
    """获取所有1000个样本"""
    all_samples = []

    for dataset in DATASETS:
        dataset_path = Path(DATA_BASE) / dataset
        if not dataset_path.exists():
            print(f"Warning: {dataset} not found at {dataset_path}")
            continue

        for subdir in sorted(dataset_path.iterdir()):
            if not subdir.is_dir():
                continue

            # 查找图片文件
            image_file = None
            for img_name in ["chart.png", "image.png", "chart.jpg", "image.jpg"]:
                img_path = subdir / img_name
                if img_path.exists():
                    image_file = str(img_path)
                    break

            if not image_file:
                for f in subdir.iterdir():
                    if f.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                        image_file = str(f)
                        break

            if not image_file:
                continue

            # 查找 ground_truth
            gt_file = subdir / "ground_truth.txt"
            ground_truth = ""
            if gt_file.exists():
                with open(gt_file, "r", encoding="utf-8") as f:
                    ground_truth = f.read().strip()

            all_samples.append({
                "id": subdir.name,
                "image_path": image_file,
                "ground_truth": ground_truth,
                "source": dataset
            })

    return all_samples


def resize_image_if_needed(image_path: str) -> Image.Image:
    """根据像素限制调整图片大小"""
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    pixels = w * h

    max_pixels = PIXEL_LIMITS["max_pixels"]
    min_pixels = PIXEL_LIMITS["min_pixels"]

    if pixels > max_pixels:
        ratio = (max_pixels / pixels) ** 0.5
        new_w, new_h = int(w * ratio), int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    elif pixels < min_pixels:
        ratio = (min_pixels / pixels) ** 0.5
        new_w, new_h = int(w * ratio), int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img


def encode_image_to_base64(image_path: str) -> str:
    """将本地图片编码为 base64"""
    img = resize_image_if_needed(image_path)

    buffer = io.BytesIO()
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
            image_base64 = encode_image_to_base64(image_path)
            mime_type = get_image_mime_type(image_path)
            image_url = f"data:{mime_type};base64,{image_base64}"

            start_time = time.time()

            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_url}},
                            {"type": "text", "text": prompt_text}
                        ]
                    }
                ],
                max_tokens=2048,
                temperature=0,
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
                time.sleep(2 ** attempt)
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
    parser = argparse.ArgumentParser(description="Qwen3-VL-30B API 全量推理")
    parser.add_argument("--prompt-cn", type=str, default="/data/finmme-bench/prompt.txt")
    parser.add_argument("--prompt-en", type=str, default="/data/finmme-bench/prompt_en.txt")
    parser.add_argument("--output-dir", type=str, default=OUTPUT_BASE)
    parser.add_argument("--workers", type=int, default=8, help="并发线程数")
    parser.add_argument("--resume", action="store_true", help="从上次中断处继续")
    args = parser.parse_args()

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # 加载提示词
    with open(args.prompt_cn, "r", encoding="utf-8") as f:
        prompt_cn = f.read().strip()
    with open(args.prompt_en, "r", encoding="utf-8") as f:
        prompt_en = f.read().strip()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{MODEL_NAME.replace('-', '_')}_results.jsonl"

    # 获取所有样本
    print("获取所有样本...")
    samples = get_all_samples()
    print(f"总样本数: {len(samples)}")

    # 按数据集统计
    source_counts = {}
    for s in samples:
        src = s.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
    print(f"数据集分布: {source_counts}")

    # 断点续传
    completed_ids = set()
    if args.resume and output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    result = json.loads(line)
                    completed_ids.add(result["id"])
                except:
                    pass
        print(f"断点续传: 已完成 {len(completed_ids)} 个样本")

    pending_samples = [s for s in samples if s["id"] not in completed_ids]

    print(f"\n{'='*60}")
    print(f"{MODEL_NAME} API 全量推理")
    print(f"{'='*60}")
    print(f"总样本数: {len(samples)}")
    print(f"待推理: {len(pending_samples)}")
    print(f"已完成: {len(completed_ids)}")
    print(f"并发数: {args.workers}")
    print(f"输出文件: {output_file}")
    print(f"{'='*60}\n")

    if not pending_samples:
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
