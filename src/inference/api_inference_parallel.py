#!/usr/bin/env python3
"""
API 并行推理脚本 - 所有模型同时并发运行
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

# API 配置
API_CONFIG = {
    "api_key": "<YOUR_API_KEY>",
    "base_url": "<YOUR_LLM_PROXY>/v1"
}

# 推理参数
INFERENCE_PARAMS = {
    "max_tokens": 2048,
    "temperature": 0
}

# 数据集配置
DATASETS = ["fin-chart_200", "finmme_200", "sync_300_cn", "sync_300_en"]


def load_prompt(prompt_path: str) -> str:
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def get_all_samples(data_base: Path) -> List[Dict]:
    all_samples = []
    for dataset in DATASETS:
        dataset_path = data_base / dataset
        if not dataset_path.exists():
            continue
        for subdir in sorted(dataset_path.iterdir()):
            if not subdir.is_dir():
                continue
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
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    ext = Path(image_path).suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "image/png")


async def infer_single(
    client: AsyncOpenAI,
    model: str,
    sample: Dict,
    prompt_cn: str,
    prompt_en: str,
    semaphore: asyncio.Semaphore,
    pbar: tqdm_asyncio
) -> Dict[str, Any]:
    """单个推理任务"""
    async with semaphore:
        sample_id = sample["id"]
        image_path = sample["image_path"]
        source = sample.get("source", "")

        prompt = prompt_cn if source == "sync_300_cn" else prompt_en
        prompt_lang = "zh" if source == "sync_300_cn" else "en"

        for attempt in range(3):
            start_time = time.time()
            try:
                image_b64 = encode_image(image_path)
                mime_type = get_image_mime_type(image_path)

                response = await client.chat.completions.create(
                    model=model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
                        ]
                    }],
                    max_tokens=INFERENCE_PARAMS["max_tokens"],
                    temperature=INFERENCE_PARAMS["temperature"]
                )

                pbar.update(1)
                return {
                    "id": sample_id,
                    "model": model,
                    "generated_text": response.choices[0].message.content,
                    "ground_truth": sample.get("ground_truth", ""),
                    "inference_time": time.time() - start_time,
                    "image_path": image_path,
                    "source": source,
                    "prompt_lang": prompt_lang,
                    "status": "success"
                }

            except Exception as e:
                if attempt == 2:
                    pbar.update(1)
                    return {
                        "id": sample_id,
                        "model": model,
                        "generated_text": "",
                        "ground_truth": sample.get("ground_truth", ""),
                        "inference_time": time.time() - start_time,
                        "image_path": image_path,
                        "source": source,
                        "prompt_lang": prompt_lang,
                        "status": "error",
                        "error": str(e)
                    }
                await asyncio.sleep(2 ** attempt)


async def run_model_inference(
    client: AsyncOpenAI,
    model: str,
    samples: List[Dict],
    prompt_cn: str,
    prompt_en: str,
    output_dir: Path,
    concurrency: int,
    pbar: tqdm_asyncio
) -> Dict:
    """单个模型的并发推理"""
    safe_model_name = model.replace("/", "_").replace(":", "_")
    output_file = output_dir / f"{safe_model_name}_results.jsonl"

    # 断点续传
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

    # 更新进度条已完成数量
    pbar.update(len(completed_ids))

    if not pending_samples:
        return {"model": model, "total": len(samples), "success": len(completed_ids), "error": 0}

    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        infer_single(client, model, sample, prompt_cn, prompt_en, semaphore, pbar)
        for sample in pending_samples
    ]

    results = await asyncio.gather(*tasks)

    # 保存结果
    with open(output_file, "a", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    success = len(completed_ids) + len([r for r in results if r.get("status") == "success"])
    error = len([r for r in results if r.get("status") == "error"])

    return {"model": model, "total": len(samples), "success": success, "error": error}


async def main_async(args):
    script_dir = Path(__file__).parent
    data_base = script_dir / "data"
    output_dir = script_dir / "outputs" / "full_1000"
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_cn = load_prompt(script_dir / "prompt.txt")
    prompt_en = load_prompt(script_dir / "prompt_en.txt")

    print("获取所有样本...")
    samples = get_all_samples(data_base)
    print(f"总样本数: {len(samples)}")

    models = args.models
    print(f"\n并行运行模型: {models}")
    print(f"每模型并发数: {args.concurrency}")
    print(f"总任务数: {len(samples) * len(models)}")

    client = AsyncOpenAI(
        api_key=API_CONFIG["api_key"],
        base_url=API_CONFIG["base_url"],
        timeout=300.0
    )

    # 为每个模型创建进度条和任务
    all_stats = {}

    # 创建所有模型的进度条
    pbars = {}
    for model in models:
        safe_name = model.replace("/", "_").replace(":", "_")[:20]
        pbars[model] = tqdm_asyncio(total=len(samples), desc=f"{safe_name}", position=models.index(model))

    # 并行运行所有模型
    tasks = [
        run_model_inference(client, model, samples, prompt_cn, prompt_en, output_dir, args.concurrency, pbars[model])
        for model in models
    ]

    results = await asyncio.gather(*tasks)

    # 关闭进度条
    for pbar in pbars.values():
        pbar.close()

    # 整理结果
    for result in results:
        all_stats[result["model"]] = result
        print(f"\n{result['model']}: 成功 {result['success']}/{result['total']}, 失败 {result['error']}")

    # 保存统计
    stats_file = output_dir / "api_inference_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(all_stats, ensure_ascii=False, fp=f, indent=2)

    print(f"\n统计信息保存至: {stats_file}")
    return all_stats


def main():
    parser = argparse.ArgumentParser(description="API 并行推理")
    parser.add_argument("--models", nargs="+", required=True, help="要运行的模型列表")
    parser.add_argument("--concurrency", type=int, default=15, help="每个模型的并发数")
    args = parser.parse_args()

    start_time = time.time()
    asyncio.run(main_async(args))
    print(f"\n总耗时: {(time.time() - start_time)/60:.2f} 分钟")


if __name__ == "__main__":
    main()
