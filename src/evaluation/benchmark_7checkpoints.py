#!/usr/bin/env python3
"""
7个LoRA检查点 Benchmark 评估脚本
- 从4个数据集各随机采样40张图片（共160张）
- 使用8卡并行 Transformers 推理
- sync_300_cn 使用中文 prompt，其他使用英文 prompt
"""
import os
os.environ['NCCL_P2P_DISABLE'] = '1'
os.environ['NCCL_IB_DISABLE'] = '1'

import torch
import json
import random
from pathlib import Path
from PIL import Image
from tqdm import tqdm
import time
import argparse
import multiprocessing as mp
from typing import List, Dict
import numpy as np

# 固定随机种子，确保可复现
RANDOM_SEED = 42

# Qwen3-VL 像素限制配置
MAX_PIXELS = 1280 * 32 * 32
MIN_PIXELS = 256 * 32 * 32

# 7个检查点配置
CHECKPOINTS = {
    "exp-005-ckpt396": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-005/checkpoint-396",
        "description": "rank32, eval_loss=0.9267, 整体最佳"
    },
    "exp-012-ckpt640": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-012/checkpoint-640",
        "description": "rank256, eval_loss=0.9335, 最大容量最佳点"
    },
    "exp-010-ckpt640": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-010/checkpoint-640",
        "description": "rank128, eval_loss=0.9429"
    },
    "exp-002-ckpt330": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-002/checkpoint-330",
        "description": "rank16, eval_loss=0.9442, 基线最佳"
    },
    "exp-009-ckpt640": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-009/checkpoint-640",
        "description": "rank64, eval_loss=0.9571"
    },
    "exp-012-ckpt800": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-012/checkpoint-800",
        "description": "rank256, eval_loss=0.9346, 最终点"
    },
    "exp-002-ckpt528": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-002/checkpoint-528",
        "description": "rank16, eval_loss=0.9474, 最终点"
    }
}

# 数据集配置
DATASETS = {
    "fin-chart_200": {"prompt_lang": "en", "sample_count": 40},
    "finmme_200": {"prompt_lang": "en", "sample_count": 40},
    "sync_300_cn": {"prompt_lang": "cn", "sample_count": 40},
    "sync_300_en": {"prompt_lang": "en", "sample_count": 40}
}


def load_prompts(prompt_cn_path: str, prompt_en_path: str) -> Dict[str, str]:
    """加载中英文 prompt"""
    with open(prompt_cn_path, 'r', encoding='utf-8') as f:
        prompt_cn = f.read().strip()
    with open(prompt_en_path, 'r', encoding='utf-8') as f:
        prompt_en = f.read().strip()
    return {"cn": prompt_cn, "en": prompt_en}


def sample_dataset(data_dir: Path, dataset_name: str, sample_count: int, seed: int) -> List[Dict]:
    """从数据集随机采样指定数量的样本"""
    dataset_path = data_dir / dataset_name
    samples = []

    # 获取所有样本目录
    sample_dirs = [d for d in dataset_path.iterdir() if d.is_dir()]

    # 设置随机种子并采样
    random.seed(seed)
    selected_dirs = random.sample(sample_dirs, min(sample_count, len(sample_dirs)))

    for sample_dir in selected_dirs:
        # 查找图片文件
        image_files = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))
        if not image_files:
            continue
        image_path = image_files[0]

        # 查找 ground truth
        analysis_file = sample_dir / "analysis.txt"
        ground_truth = ""
        if analysis_file.exists():
            with open(analysis_file, 'r', encoding='utf-8') as f:
                ground_truth = f.read().strip()

        samples.append({
            "id": sample_dir.name,
            "image_path": str(image_path),
            "ground_truth": ground_truth,
            "source": dataset_name,
            "prompt_lang": DATASETS[dataset_name]["prompt_lang"]
        })

    return samples


def build_sample_index(data_dir: Path, seed: int) -> List[Dict]:
    """构建采样索引"""
    all_samples = []

    for dataset_name, config in DATASETS.items():
        samples = sample_dataset(data_dir, dataset_name, config["sample_count"], seed)
        all_samples.extend(samples)
        print(f"  {dataset_name}: {len(samples)} samples (prompt: {config['prompt_lang']})")

    return all_samples


def split_dataset(samples: List[Dict], num_groups: int) -> List[List[Dict]]:
    """将数据集均匀分片"""
    num_samples = len(samples)
    base_size = num_samples // num_groups
    remainder = num_samples % num_groups

    splits = []
    start = 0
    for i in range(num_groups):
        size = base_size + (1 if i < remainder else 0)
        splits.append(samples[start:start + size])
        start += size
    return splits


def inference_worker(
    gpu_id: int,
    base_model_path: str,
    lora_path: str,
    model_name: str,
    samples: List[Dict],
    prompts: Dict[str, str],
    output_dir: Path
):
    """单GPU推理worker"""
    try:
        os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)

        print(f"[GPU {gpu_id}] 启动，样本数: {len(samples)}")

        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
        from peft import PeftModel

        # 加载基础模型
        print(f"[GPU {gpu_id}] 加载基础模型...")
        base_model = Qwen3VLForConditionalGeneration.from_pretrained(
            base_model_path,
            torch_dtype=torch.bfloat16,
            device_map="cuda:0",
            attn_implementation="eager"
        )

        # 加载 LoRA
        print(f"[GPU {gpu_id}] 加载 LoRA: {lora_path}")
        model = PeftModel.from_pretrained(base_model, lora_path)
        model = model.merge_and_unload()

        processor = AutoProcessor.from_pretrained(base_model_path)

        # 设置 max_pixels 限制
        processor.image_processor.size = {
            "longest_edge": MAX_PIXELS,
            "shortest_edge": MIN_PIXELS
        }
        processor.image_processor.max_pixels = MAX_PIXELS
        processor.image_processor.min_pixels = MIN_PIXELS

        mem = torch.cuda.memory_allocated(0) / 1024**3
        print(f"[GPU {gpu_id}] 显存: {mem:.2f} GB")

        results = []

        for sample in tqdm(samples, desc=f"GPU {gpu_id}", position=gpu_id):
            try:
                image = Image.open(sample["image_path"]).convert("RGB")

                # 根据样本选择对应语言的 prompt
                prompt_text = prompts[sample["prompt_lang"]]

                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": prompt_text}
                        ]
                    }
                ]

                text_prompt = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                inputs = processor(
                    text=[text_prompt], images=[image], return_tensors="pt"
                ).to(model.device)

                start_time = time.time()
                with torch.no_grad():
                    outputs = model.generate(**inputs, max_new_tokens=2048, do_sample=False)
                inference_time = time.time() - start_time

                generated_text = processor.decode(
                    outputs[0][inputs['input_ids'].shape[1]:],
                    skip_special_tokens=True
                )

                results.append({
                    "id": sample["id"],
                    "model": model_name,
                    "gpu_id": gpu_id,
                    "generated_text": generated_text,
                    "ground_truth": sample.get("ground_truth", ""),
                    "inference_time": inference_time,
                    "image_path": sample["image_path"],
                    "source": sample.get("source", ""),
                    "prompt_lang": sample.get("prompt_lang", "en")
                })

                del inputs, outputs
                torch.cuda.empty_cache()

            except Exception as e:
                print(f"[GPU {gpu_id}] ✗ {sample['id']} 失败: {e}")
                results.append({
                    "id": sample["id"],
                    "model": model_name,
                    "gpu_id": gpu_id,
                    "error": str(e),
                    "image_path": sample["image_path"],
                    "source": sample.get("source", ""),
                    "prompt_lang": sample.get("prompt_lang", "en")
                })
                torch.cuda.empty_cache()

        # 保存结果
        output_file = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        with open(output_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        print(f"[GPU {gpu_id}] ✓ 完成，结果: {output_file}")

    except Exception as e:
        print(f"[GPU {gpu_id}] ✗✗ Worker失败: {e}")
        import traceback
        traceback.print_exc()


def merge_results(output_dir: Path, model_name: str, num_gpus: int):
    """合并结果"""
    all_results = []

    for gpu_id in range(num_gpus):
        result_file = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        if result_file.exists():
            with open(result_file) as f:
                for line in f:
                    all_results.append(json.loads(line))

    all_results.sort(key=lambda x: x["id"])

    merged_file = output_dir / f"{model_name}_results.jsonl"
    with open(merged_file, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = [r for r in all_results if "error" not in r]
    failed = [r for r in all_results if "error" in r]

    # 按来源统计
    source_stats = {}
    for r in success:
        source = r.get("source", "unknown")
        if source not in source_stats:
            source_stats[source] = {"count": 0, "total_time": 0}
        source_stats[source]["count"] += 1
        source_stats[source]["total_time"] += r["inference_time"]

    stats = {
        "model": model_name,
        "mode": f"{num_gpus}gpu_parallel",
        "total_samples": len(all_results),
        "success_count": len(success),
        "failed_count": len(failed),
        "success_rate": len(success) / len(all_results) if all_results else 0,
        "avg_inference_time": float(np.mean([r["inference_time"] for r in success])) if success else 0,
        "total_time": sum([r["inference_time"] for r in success]),
        "source_breakdown": {
            k: {"count": v["count"], "avg_time": v["total_time"] / v["count"]}
            for k, v in source_stats.items()
        }
    }

    stats_file = output_dir / f"{model_name}_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"{model_name} 推理完成")
    print(f"{'='*60}")
    print(f"总样本数: {stats['total_samples']}")
    print(f"成功: {stats['success_count']} | 失败: {stats['failed_count']}")
    print(f"成功率: {stats['success_rate']:.2%}")
    print(f"平均推理时间: {stats['avg_inference_time']:.2f}s")
    print(f"总推理时间: {stats['total_time']:.1f}s ({stats['total_time']/60:.1f}min)")
    print(f"\n按来源统计:")
    for source, data in stats["source_breakdown"].items():
        print(f"  {source}: {data['count']}个, 平均{data['avg_time']:.2f}s")
    print(f"{'='*60}\n")

    # 清理临时文件
    for gpu_id in range(num_gpus):
        tmp_file = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        if tmp_file.exists():
            tmp_file.unlink()

    return stats


def run_single_checkpoint(
    checkpoint_name: str,
    samples: List[Dict],
    prompts: Dict[str, str],
    output_dir: Path,
    num_gpus: int
):
    """运行单个检查点的推理"""
    config = CHECKPOINTS[checkpoint_name]
    base_model_path = config["base_model"]
    lora_path = config["lora_path"]

    print(f"\n{'='*60}")
    print(f"开始推理: {checkpoint_name}")
    print(f"{'='*60}")
    print(f"基座模型: {base_model_path}")
    print(f"LoRA路径: {lora_path}")
    print(f"说明: {config['description']}")
    print(f"样本总数: {len(samples)}")
    print(f"GPU数量: {num_gpus}")
    print(f"{'='*60}\n")

    sample_splits = split_dataset(samples, num_gpus)

    processes = []
    for gpu_id in range(num_gpus):
        p = mp.Process(
            target=inference_worker,
            args=(gpu_id, base_model_path, lora_path, checkpoint_name,
                  sample_splits[gpu_id], prompts, output_dir)
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    stats = merge_results(output_dir, checkpoint_name, num_gpus)
    return stats


def main():
    parser = argparse.ArgumentParser(description="7个LoRA检查点 Benchmark 评估")
    parser.add_argument("--data-dir", type=str, default="/data/finmme-bench/data",
                        help="数据目录路径")
    parser.add_argument("--prompt-cn", type=str, default="/data/finmme-bench/prompt.txt",
                        help="中文 prompt 文件")
    parser.add_argument("--prompt-en", type=str, default="/data/finmme-bench/prompt_en.txt",
                        help="英文 prompt 文件")
    parser.add_argument("--output-dir", type=str, default="/data/finmme-bench/outputs/benchmark_7ckpt",
                        help="输出目录")
    parser.add_argument("--num-gpus", type=int, default=8)
    parser.add_argument("--checkpoint", type=str, default=None,
                        choices=list(CHECKPOINTS.keys()),
                        help="只运行指定检查点（不指定则运行全部）")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED,
                        help="随机种子")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 加载 prompts
    print("加载 prompts...")
    prompts = load_prompts(args.prompt_cn, args.prompt_en)

    # 构建采样索引
    print(f"\n从4个数据集各采样40张（随机种子: {args.seed}）...")
    samples = build_sample_index(data_dir, args.seed)
    print(f"总样本数: {len(samples)}")

    # 保存采样索引
    index_file = output_dir / "sample_index.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    print(f"采样索引已保存: {index_file}")

    # 运行推理
    all_stats = {}
    checkpoints_to_run = [args.checkpoint] if args.checkpoint else list(CHECKPOINTS.keys())

    for i, ckpt_name in enumerate(checkpoints_to_run):
        print(f"\n[{i+1}/{len(checkpoints_to_run)}] 处理检查点: {ckpt_name}")
        stats = run_single_checkpoint(ckpt_name, samples, prompts, output_dir, args.num_gpus)
        all_stats[ckpt_name] = stats

    # 保存汇总统计
    summary_file = output_dir / "benchmark_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, ensure_ascii=False, indent=2)

    # 打印汇总
    print(f"\n{'='*70}")
    print("Benchmark 汇总")
    print(f"{'='*70}")
    print(f"{'检查点':<25} {'成功率':>10} {'平均时间':>12} {'总时间':>12}")
    print(f"{'-'*70}")
    for ckpt_name, stats in all_stats.items():
        print(f"{ckpt_name:<25} {stats['success_rate']:>9.1%} {stats['avg_inference_time']:>10.2f}s {stats['total_time']:>10.1f}s")
    print(f"{'='*70}")
    print(f"结果保存在: {output_dir}")


if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    main()
