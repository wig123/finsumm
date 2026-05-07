#!/usr/bin/env python3
"""
FinMME Benchmark - 全量1000样本推理
模型：3个最佳checkpoint + base模型 (Qwen3-VL-8B-Instruct)
"""
import os
import sys
import json
import time
import argparse
import torch
import torch.multiprocessing as mp
from pathlib import Path
from typing import Dict, List, Optional
from tqdm import tqdm
from PIL import Image

# 设置多进程启动方式
mp.set_start_method('spawn', force=True)

# 基础配置
BASE_MODEL = "$MODEL_ROOT/qwen3-vl-8b-instruct"
DATA_BASE = "/data/finmme-bench/data"
OUTPUT_BASE = "/data/finmme-bench/outputs/full_1000"

# 模型配置：3个最佳checkpoint + base模型
MODELS = {
    "base": {
        "lora_path": None,  # 不使用LoRA
        "description": "Qwen3-VL-8B-Instruct (base, no LoRA)"
    },
    "exp-012-ckpt640": {
        "lora_path": "$DATA_ROOT/sft/outputs/exp-012/checkpoint-640",
        "description": "rank256, eval_loss=0.9335, Judge=0.7538 (TOP1)"
    },
    "exp-012-ckpt800": {
        "lora_path": "$DATA_ROOT/sft/outputs/exp-012/checkpoint-800",
        "description": "rank256, eval_loss=0.9346, Judge=0.7445 (TOP2)"
    },
    "exp-010-ckpt640": {
        "lora_path": "$DATA_ROOT/sft/outputs/exp-010/checkpoint-640",
        "description": "rank128, eval_loss=0.9429, Judge=0.7370 (TOP3)"
    }
}

# 数据集配置
DATASETS = ["fin-chart_200", "finmme_200", "sync_300_cn", "sync_300_en"]

# 像素限制 - 与训练保持一致
PIXEL_LIMITS = {
    "max_pixels": 1280 * 32 * 32,
    "min_pixels": 256 * 32 * 32,
}


def get_all_samples() -> List[Dict]:
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


def load_model_and_processor(model_name: str, model_config: Dict, device: str):
    """加载模型和处理器"""
    from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
    from peft import PeftModel

    processor = AutoProcessor.from_pretrained(
        BASE_MODEL,
        max_pixels=PIXEL_LIMITS["max_pixels"],
        min_pixels=PIXEL_LIMITS["min_pixels"],
    )

    # 加载基础模型 - 使用sdpa避免flash_attention依赖问题
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map=device,
        attn_implementation="sdpa",
    )

    # 如果有LoRA，加载LoRA权重
    lora_path = model_config.get("lora_path")
    if lora_path:
        print(f"  Loading LoRA from: {lora_path}")
        model = PeftModel.from_pretrained(model, lora_path)
        model = model.merge_and_unload()

    model.eval()
    return model, processor


def inference_worker(
    gpu_id: int,
    model_name: str,
    model_config: Dict,
    samples: List[Dict],
    prompt_cn: str,
    prompt_en: str,
    output_file: str,
    progress_queue: mp.Queue
):
    """单GPU推理worker"""
    device = f"cuda:{gpu_id}"
    torch.cuda.set_device(gpu_id)

    try:
        model, processor = load_model_and_processor(model_name, model_config, device)
    except Exception as e:
        print(f"GPU {gpu_id}: Failed to load model: {e}")
        return

    results = []
    for sample in samples:
        sample_id = sample["id"]
        image_path = sample["image_path"]
        source = sample.get("source", "")

        # 选择提示词
        if source == "sync_300_cn":
            prompt_text = prompt_cn
            prompt_lang = "zh"
        else:
            prompt_text = prompt_en
            prompt_lang = "en"

        try:
            image = Image.open(image_path).convert("RGB")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt_text}
                    ]
                }
            ]

            text = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

            inputs = processor(
                text=[text],
                images=[image],
                padding=True,
                return_tensors="pt"
            ).to(device)

            start_time = time.time()

            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=2048,
                    do_sample=False,
                    pad_token_id=processor.tokenizer.pad_token_id,
                )

            inference_time = time.time() - start_time

            generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
            generated_text = processor.decode(generated_ids, skip_special_tokens=True)

            result = {
                "id": sample_id,
                "model": model_name,
                "generated_text": generated_text,
                "ground_truth": sample.get("ground_truth", ""),
                "inference_time": inference_time,
                "image_path": image_path,
                "source": source,
                "prompt_lang": prompt_lang,
            }

        except Exception as e:
            result = {
                "id": sample_id,
                "model": model_name,
                "error": str(e),
                "image_path": image_path,
                "source": source,
            }

        results.append(result)
        progress_queue.put(1)

        # 实时保存
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    # 清理
    del model
    torch.cuda.empty_cache()


def run_inference_for_model(
    model_name: str,
    model_config: Dict,
    samples: List[Dict],
    prompt_cn: str,
    prompt_en: str,
    output_dir: Path,
    num_gpus: int = 8
):
    """对单个模型运行推理"""
    output_file = output_dir / f"{model_name}_results.jsonl"

    # 检查已完成的样本（断点续传）
    completed_ids = set()
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    completed_ids.add(r["id"])
                except:
                    pass

    pending_samples = [s for s in samples if s["id"] not in completed_ids]

    print(f"\n{'='*60}")
    print(f"模型: {model_name}")
    print(f"描述: {model_config['description']}")
    print(f"总样本: {len(samples)} | 已完成: {len(completed_ids)} | 待推理: {len(pending_samples)}")
    print(f"{'='*60}")

    if not pending_samples:
        print("所有样本已完成！")
        return

    # 分配样本到各GPU
    samples_per_gpu = [[] for _ in range(num_gpus)]
    for i, sample in enumerate(pending_samples):
        samples_per_gpu[i % num_gpus].append(sample)

    # 创建进度队列
    progress_queue = mp.Queue()

    # 启动多进程
    processes = []
    for gpu_id in range(num_gpus):
        if not samples_per_gpu[gpu_id]:
            continue
        p = mp.Process(
            target=inference_worker,
            args=(
                gpu_id,
                model_name,
                model_config,
                samples_per_gpu[gpu_id],
                prompt_cn,
                prompt_en,
                str(output_file),
                progress_queue
            )
        )
        p.start()
        processes.append(p)

    # 进度条
    with tqdm(total=len(pending_samples), desc=f"{model_name} 推理") as pbar:
        completed = 0
        while completed < len(pending_samples):
            try:
                progress_queue.get(timeout=300)
                completed += 1
                pbar.update(1)
            except:
                # 检查进程是否还活着
                alive = any(p.is_alive() for p in processes)
                if not alive:
                    break

    # 等待所有进程完成
    for p in processes:
        p.join()

    # 统计结果
    results = []
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            results.append(json.loads(line))

    success = len([r for r in results if "error" not in r])
    failed = len([r for r in results if "error" in r])

    stats = {
        "model": model_name,
        "description": model_config["description"],
        "total_samples": len(samples),
        "success_count": success,
        "failed_count": failed,
        "success_rate": success / len(samples) if samples else 0,
    }

    stats_file = output_dir / f"{model_name}_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n✓ {model_name} 完成: 成功 {success}/{len(samples)}")


def main():
    parser = argparse.ArgumentParser(description="FinMME 全量1000样本推理")
    parser.add_argument("--prompt-cn", type=str, default="/data/finmme-bench/prompt.txt")
    parser.add_argument("--prompt-en", type=str, default="/data/finmme-bench/prompt_en.txt")
    parser.add_argument("--output-dir", type=str, default=OUTPUT_BASE)
    parser.add_argument("--num-gpus", type=int, default=8)
    parser.add_argument("--models", type=str, nargs="+", default=None,
                        help="指定要运行的模型，默认运行所有")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 加载提示词
    with open(args.prompt_cn, "r", encoding="utf-8") as f:
        prompt_cn = f.read().strip()
    with open(args.prompt_en, "r", encoding="utf-8") as f:
        prompt_en = f.read().strip()

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

    # 保存样本索引
    index_file = output_dir / "sample_index.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)

    # 确定要运行的模型
    models_to_run = args.models if args.models else list(MODELS.keys())

    print(f"\n待运行模型: {models_to_run}")
    print(f"GPU数量: {args.num_gpus}")
    print(f"输出目录: {output_dir}")

    # 依次运行每个模型
    for model_name in models_to_run:
        if model_name not in MODELS:
            print(f"Warning: 未知模型 {model_name}，跳过")
            continue

        run_inference_for_model(
            model_name=model_name,
            model_config=MODELS[model_name],
            samples=samples,
            prompt_cn=prompt_cn,
            prompt_en=prompt_en,
            output_dir=output_dir,
            num_gpus=args.num_gpus
        )

    # 生成总结
    print("\n" + "="*60)
    print("全部推理完成！")
    print("="*60)

    summary = {"models": {}}
    for model_name in models_to_run:
        stats_file = output_dir / f"{model_name}_stats.json"
        if stats_file.exists():
            with open(stats_file) as f:
                summary["models"][model_name] = json.load(f)

    summary_file = output_dir / "full_benchmark_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"汇总文件: {summary_file}")


if __name__ == "__main__":
    main()
