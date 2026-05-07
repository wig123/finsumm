#!/usr/bin/env python3
"""
API 异步并行推理脚本
使用 API 易调用多个视觉语言模型进行金融图表分析
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

# 推理参数
INFERENCE_PARAMS = {
    "max_tokens": 8192,
    "temperature": 0  # 确定性输出
}


def load_prompt(prompt_path: str) -> str:
    """加载提示词"""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_dataset(dataset_path: str) -> List[Dict]:
    """加载数据集索引"""
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def encode_image(image_path: str) -> str:
    """将图片编码为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def infer_single(
    client: AsyncOpenAI,
    model: str,
    image_path: str,
    prompt: str,
    sample_id: str,
    semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    """单个模型单个样本的推理"""
    async with semaphore:
        start_time = time.time()

        try:
            # 编码图片
            image_b64 = encode_image(image_path)

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
                                "url": f"data:image/png;base64,{image_b64}"
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
                "inference_time": inference_time,
                "image_path": image_path,
                "status": "success",
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0
                }
            }

        except Exception as e:
            inference_time = time.time() - start_time
            return {
                "id": sample_id,
                "model": model,
                "generated_text": "",
                "inference_time": inference_time,
                "image_path": image_path,
                "status": "error",
                "error": str(e)
            }


async def infer_sample_all_models(
    client: AsyncOpenAI,
    sample: Dict,
    prompt: str,
    models: List[str],
    semaphore: asyncio.Semaphore
) -> List[Dict[str, Any]]:
    """单个样本在所有模型上并行推理"""
    tasks = [
        infer_single(
            client, model, sample["image_path"],
            prompt, sample["id"], semaphore
        )
        for model in models
    ]
    return await asyncio.gather(*tasks)


async def run_inference(
    samples: List[Dict],
    prompt: str,
    models: List[str],
    output_dir: Path,
    concurrency: int = 15
):
    """运行完整推理流程"""

    # 创建客户端
    client = AsyncOpenAI(
        api_key=API_CONFIG["api_key"],
        base_url=API_CONFIG["base_url"],
        timeout=300.0  # 5分钟超时
    )

    # 并发控制
    semaphore = asyncio.Semaphore(concurrency)

    # 按模型分组的结果
    results_by_model = {model: [] for model in models}

    # 统计信息
    stats = {
        model: {
            "total": len(samples),
            "success": 0,
            "error": 0,
            "total_time": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0
        }
        for model in models
    }

    print(f"\n开始推理:")
    print(f"  - 样本数: {len(samples)}")
    print(f"  - 模型数: {len(models)}")
    print(f"  - 并发数: {concurrency}")
    print(f"  - 总任务数: {len(samples) * len(models)}\n")

    # 创建所有任务
    all_tasks = []
    for sample in samples:
        for model in models:
            task = infer_single(
                client, model, sample["image_path"],
                prompt, sample["id"], semaphore
            )
            all_tasks.append(task)

    # 执行所有任务并显示进度
    results = await tqdm_asyncio.gather(*all_tasks, desc="推理进度")

    # 整理结果
    for result in results:
        model = result["model"]
        results_by_model[model].append(result)

        # 更新统计
        if result["status"] == "success":
            stats[model]["success"] += 1
        else:
            stats[model]["error"] += 1

        stats[model]["total_time"] += result["inference_time"]
        if "usage" in result:
            stats[model]["total_prompt_tokens"] += result["usage"].get("prompt_tokens", 0)
            stats[model]["total_completion_tokens"] += result["usage"].get("completion_tokens", 0)

    # 保存结果
    output_dir.mkdir(parents=True, exist_ok=True)

    for model in models:
        # 生成安全的文件名
        safe_model_name = model.replace("/", "_").replace(":", "_")

        # 保存 JSONL 结果
        results_file = output_dir / f"{safe_model_name}_api_results.jsonl"
        with open(results_file, "w", encoding="utf-8") as f:
            for result in results_by_model[model]:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

        # 计算统计信息
        model_stats = stats[model]
        avg_time = model_stats["total_time"] / model_stats["total"] if model_stats["total"] > 0 else 0

        print(f"\n{model}:")
        print(f"  成功: {model_stats['success']}/{model_stats['total']}")
        print(f"  失败: {model_stats['error']}")
        print(f"  平均耗时: {avg_time:.2f}s")
        print(f"  总 tokens: {model_stats['total_prompt_tokens'] + model_stats['total_completion_tokens']}")
        print(f"  结果保存至: {results_file}")

    # 保存统计信息
    stats_file = output_dir / "api_inference_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, ensure_ascii=False, fp=f, indent=2)

    print(f"\n统计信息保存至: {stats_file}")

    return results_by_model, stats


def main():
    parser = argparse.ArgumentParser(description="API 异步并行推理")
    parser.add_argument(
        "--dataset",
        default="dataset_index.json",
        help="数据集索引文件路径"
    )
    parser.add_argument(
        "--prompt",
        default="prompt.txt",
        help="提示词文件路径"
    )
    parser.add_argument(
        "--output",
        default="outputs",
        help="输出目录"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=MODELS,
        help="要测试的模型列表"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=15,
        help="并发请求数"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制样本数量（用于测试）"
    )

    args = parser.parse_args()

    # 获取脚本所在目录
    script_dir = Path(__file__).parent

    # 加载数据
    dataset_path = script_dir / args.dataset
    prompt_path = script_dir / args.prompt
    output_dir = script_dir / args.output

    print("加载数据...")
    samples = load_dataset(dataset_path)
    prompt = load_prompt(prompt_path)

    # 限制样本数
    if args.limit:
        samples = samples[:args.limit]
        print(f"限制样本数: {args.limit}")

    print(f"数据集: {len(samples)} 样本")
    print(f"模型: {args.models}")

    # 运行推理
    start_time = time.time()

    asyncio.run(run_inference(
        samples=samples,
        prompt=prompt,
        models=args.models,
        output_dir=output_dir,
        concurrency=args.concurrency
    ))

    total_time = time.time() - start_time
    print(f"\n总耗时: {total_time/60:.2f} 分钟")


if __name__ == "__main__":
    main()
