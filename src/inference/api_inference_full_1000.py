#!/usr/bin/env python3
"""
API 异步并行推理脚本 - 全量1000样本
支持双语提示词 (sync_300_cn 用中文，其他用英文)
与 GPU 推理保持一致的配置
"""

import asyncio
import json
import base64
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any
from tqdm.asyncio import tqdm_asyncio
from openai import AsyncOpenAI

# API 易配置
API_CONFIG = {
    "api_key": "<YOUR_API_KEY>",
    "base_url": "<YOUR_LLM_PROXY>/v1"
}

# 待测试模型
MODELS = [
    "qwen3-vl-235b-a22b-instruct",
    "glm-4.6v",
    "gemini-2.5-flash-preview-09-2025",
    "gpt-5-mini"
]

# 推理参数 - 与 GPU 推理一致
INFERENCE_PARAMS = {
    "max_tokens": 2048,  # 与 GPU 推理一致
    "temperature": 0     # 确定性输出 (对应 do_sample=False)
}

# 数据集配置
DATASETS = ["fin-chart_200", "finmme_200", "sync_300_cn", "sync_300_en"]


def load_prompt(prompt_path: str) -> str:
    """加载提示词"""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def get_all_samples(data_base: Path) -> List[Dict]:
    """获取所有1000个样本"""
    all_samples = []

    for dataset in DATASETS:
        dataset_path = data_base / dataset
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
            # sync_300_cn 使用中文 analysis.txt
            # 其他数据集：优先 analysis_en.txt，否则 analysis.txt
            ground_truth = ""
            if dataset == "sync_300_cn":
                gt_file = subdir / "analysis.txt"
            else:
                gt_file = subdir / "analysis_en.txt"
                if not gt_file.exists():
                    gt_file = subdir / "analysis.txt"

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


def encode_image(image_path: str) -> str:
    """将图片编码为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """获取图片的 MIME 类型"""
    ext = Path(image_path).suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp"
    }
    return mime_map.get(ext, "image/png")


async def infer_single(
    client: AsyncOpenAI,
    model: str,
    sample: Dict,
    prompt_cn: str,
    prompt_en: str,
    semaphore: asyncio.Semaphore,
    retry_count: int = 3
) -> Dict[str, Any]:
    """单个模型单个样本的推理"""
    async with semaphore:
        sample_id = sample["id"]
        image_path = sample["image_path"]
        source = sample.get("source", "")

        # 选择提示词 - 与 GPU 推理一致
        if source == "sync_300_cn":
            prompt = prompt_cn
            prompt_lang = "zh"
        else:
            prompt = prompt_en
            prompt_lang = "en"

        for attempt in range(retry_count):
            start_time = time.time()

            try:
                # 编码图片
                image_b64 = encode_image(image_path)
                mime_type = get_image_mime_type(image_path)

                # 调用 API
                response = await client.chat.completions.create(
                    model=model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_b64}"
                                }
                            }
                        ]
                    }],
                    max_tokens=INFERENCE_PARAMS["max_tokens"],
                    temperature=INFERENCE_PARAMS["temperature"]
                )

                inference_time = time.time() - start_time

                return {
                    "id": sample_id,
                    "model": model,
                    "generated_text": response.choices[0].message.content,
                    "ground_truth": sample.get("ground_truth", ""),
                    "inference_time": inference_time,
                    "image_path": image_path,
                    "source": source,
                    "prompt_lang": prompt_lang,
                    "status": "success",
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0
                    }
                }

            except Exception as e:
                inference_time = time.time() - start_time
                error_msg = str(e)

                # 如果是最后一次尝试，返回错误
                if attempt == retry_count - 1:
                    return {
                        "id": sample_id,
                        "model": model,
                        "generated_text": "",
                        "ground_truth": sample.get("ground_truth", ""),
                        "inference_time": inference_time,
                        "image_path": image_path,
                        "source": source,
                        "prompt_lang": prompt_lang,
                        "status": "error",
                        "error": error_msg
                    }

                # 等待后重试
                await asyncio.sleep(2 ** attempt)


async def run_inference_for_model(
    client: AsyncOpenAI,
    model: str,
    samples: List[Dict],
    prompt_cn: str,
    prompt_en: str,
    output_dir: Path,
    concurrency: int = 10
) -> Dict:
    """对单个模型运行推理"""
    safe_model_name = model.replace("/", "_").replace(":", "_")
    output_file = output_dir / f"{safe_model_name}_results.jsonl"

    # 检查已完成的样本（断点续传）
    completed_ids = set()
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if r.get("status") == "success":
                        completed_ids.add(r["id"])
                except:
                    pass

    pending_samples = [s for s in samples if s["id"] not in completed_ids]

    print(f"\n{'='*60}")
    print(f"模型: {model}")
    print(f"总样本: {len(samples)} | 已完成: {len(completed_ids)} | 待推理: {len(pending_samples)}")
    print(f"{'='*60}")

    if not pending_samples:
        print("所有样本已完成！")
        # 返回已有统计
        results = []
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    results.append(json.loads(line))
                except:
                    pass
        success = len([r for r in results if r.get("status") == "success"])
        return {
            "model": model,
            "total": len(samples),
            "success": success,
            "error": len(samples) - success
        }

    # 并发控制
    semaphore = asyncio.Semaphore(concurrency)

    # 创建所有任务
    tasks = [
        infer_single(client, model, sample, prompt_cn, prompt_en, semaphore)
        for sample in pending_samples
    ]

    # 执行所有任务
    results = await tqdm_asyncio.gather(*tasks, desc=f"{model} 推理")

    # 追加保存结果
    with open(output_file, "a", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    # 统计
    all_results = []
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                all_results.append(json.loads(line))
            except:
                pass

    success = len([r for r in all_results if r.get("status") == "success"])
    error = len([r for r in all_results if r.get("status") == "error"])

    print(f"✓ {model} 完成: 成功 {success}/{len(samples)}, 失败 {error}")

    return {
        "model": model,
        "total": len(samples),
        "success": success,
        "error": error
    }


async def main_async(args):
    """异步主函数"""
    script_dir = Path(__file__).parent
    data_base = script_dir / "data"
    output_dir = script_dir / "outputs" / "full_1000"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 加载双语提示词
    prompt_cn = load_prompt(script_dir / "prompt.txt")
    prompt_en = load_prompt(script_dir / "prompt_en.txt")

    # 获取所有样本
    print("获取所有样本...")
    samples = get_all_samples(data_base)
    print(f"总样本数: {len(samples)}")

    # 按数据集统计
    source_counts = {}
    for s in samples:
        src = s.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
    print(f"数据集分布: {source_counts}")

    # 限制样本数（测试用）
    if args.limit:
        samples = samples[:args.limit]
        print(f"限制样本数: {args.limit}")

    # 确定要运行的模型
    models = args.models if args.models else MODELS
    print(f"\n待运行模型: {models}")
    print(f"并发数: {args.concurrency}")

    # 创建客户端
    client = AsyncOpenAI(
        api_key=API_CONFIG["api_key"],
        base_url=API_CONFIG["base_url"],
        timeout=300.0
    )

    # 依次运行每个模型
    all_stats = {}
    for model in models:
        stats = await run_inference_for_model(
            client=client,
            model=model,
            samples=samples,
            prompt_cn=prompt_cn,
            prompt_en=prompt_en,
            output_dir=output_dir,
            concurrency=args.concurrency
        )
        all_stats[model] = stats

    # 保存统计信息
    stats_file = output_dir / "api_inference_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(all_stats, ensure_ascii=False, fp=f, indent=2)

    print(f"\n{'='*60}")
    print("全部推理完成！")
    print(f"统计信息保存至: {stats_file}")
    print(f"{'='*60}")

    return all_stats


def main():
    parser = argparse.ArgumentParser(description="API 全量1000样本推理")
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="要测试的模型列表"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="并发请求数"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制样本数量（用于测试）"
    )

    args = parser.parse_args()

    start_time = time.time()
    asyncio.run(main_async(args))
    total_time = time.time() - start_time
    print(f"\n总耗时: {total_time/60:.2f} 分钟")


if __name__ == "__main__":
    main()
