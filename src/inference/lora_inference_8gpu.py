#!/usr/bin/env python3
"""
LoRA 模型 8卡并行推理脚本
支持: exp-002, exp-005 等 LoRA 微调模型
基座模型: Qwen3-VL-8B-Instruct

统一使用 max_pixels 限制，确保所有样本公平对比
"""
import os
os.environ['NCCL_P2P_DISABLE'] = '1'
os.environ['NCCL_IB_DISABLE'] = '1'

import torch
import json
from pathlib import Path
from PIL import Image
from tqdm import tqdm
import time
import argparse
import multiprocessing as mp
from typing import List, Dict
import numpy as np

# Qwen3-VL 像素限制配置 (patch_size=16)
MAX_PIXELS = 1280 * 32 * 32  # ~1,310,720 pixels
MIN_PIXELS = 256 * 32 * 32   # ~262,144 pixels

# LoRA 模型配置
LORA_MODELS = {
    "exp-002": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-002/checkpoint-330",
        "description": "8 epochs, best at epoch 5"
    },
    "exp-005": {
        "base_model": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "lora_path": "$DATA_ROOT/sft/outputs/exp-005/checkpoint-396",
        "description": "rank 32, best at epoch 3"
    }
}

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
    prompt_text: str,
    output_dir: Path
):
    """单GPU推理worker (LoRA 模型单卡可跑)"""
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

        # 设置 max_pixels 限制，避免大图片 OOM
        processor.image_processor.size = {
            "longest_edge": MAX_PIXELS,
            "shortest_edge": MIN_PIXELS
        }
        processor.image_processor.max_pixels = MAX_PIXELS
        processor.image_processor.min_pixels = MIN_PIXELS
        print(f"[GPU {gpu_id}] max_pixels: {MAX_PIXELS:,}")

        mem = torch.cuda.memory_allocated(0) / 1024**3
        print(f"[GPU {gpu_id}] 显存: {mem:.2f} GB")

        results = []

        for sample in tqdm(samples, desc=f"GPU {gpu_id}", position=gpu_id):
            try:
                image = Image.open(sample["image_path"]).convert("RGB")

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
                    "source": sample.get("source", "")
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
                    "source": sample.get("source", "")
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

def main():
    parser = argparse.ArgumentParser(description="LoRA模型8卡并行推理")
    parser.add_argument("--model", type=str, required=True, choices=list(LORA_MODELS.keys()),
                        help="LoRA模型名称: exp-002, exp-005")
    parser.add_argument("--dataset", type=str, default="/data/finmme-bench/dataset_index_485.json")
    parser.add_argument("--prompt", type=str, default="/data/finmme-bench/prompt.txt")
    parser.add_argument("--output-dir", type=str, default="/data/finmme-bench/outputs")
    parser.add_argument("--num-gpus", type=int, default=8)
    args = parser.parse_args()

    model_config = LORA_MODELS[args.model]
    base_model_path = model_config["base_model"]
    lora_path = model_config["lora_path"]
    model_name = args.model

    with open(args.dataset) as f:
        samples = json.load(f)

    with open(args.prompt) as f:
        prompt_text = f.read().strip()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    num_gpus = args.num_gpus
    print(f"\n{'='*60}")
    print(f"{model_name} LoRA 8卡并行推理")
    print(f"{'='*60}")
    print(f"基座模型: {base_model_path}")
    print(f"LoRA路径: {lora_path}")
    print(f"说明: {model_config['description']}")
    print(f"样本总数: {len(samples)}")
    print(f"每GPU样本数: ~{len(samples) // num_gpus}")
    print(f"{'='*60}\n")

    sample_splits = split_dataset(samples, num_gpus)

    processes = []
    for gpu_id in range(num_gpus):
        p = mp.Process(
            target=inference_worker,
            args=(gpu_id, base_model_path, lora_path, model_name,
                  sample_splits[gpu_id], prompt_text, output_dir)
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    merge_results(output_dir, model_name, num_gpus)

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    main()
