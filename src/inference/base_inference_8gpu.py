#!/usr/bin/env python3
"""
8卡并行基础模型推理脚本 - 无LoRA，原始Qwen3-VL-8B
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
    gpu_pair: tuple,
    group_id: int,
    model_path: str,
    samples: List[Dict],
    prompt_text: str,
    output_dir: Path
):
    """双GPU推理worker - 基础模型"""
    try:
        gpu_str = f"{gpu_pair[0]},{gpu_pair[1]}"
        os.environ['CUDA_VISIBLE_DEVICES'] = gpu_str

        print(f"[Group {group_id}] GPU {gpu_pair} 启动，样本数: {len(samples)}")

        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor

        # 加载基础模型 (无LoRA)
        print(f"[Group {group_id}] 加载基础模型 (无LoRA)...")
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="eager"
        )

        processor = AutoProcessor.from_pretrained(model_path)

        for i in range(2):
            mem = torch.cuda.memory_allocated(i) / 1024**3
            print(f"[Group {group_id}] cuda:{i} 显存: {mem:.2f} GB")

        results = []

        for sample in tqdm(samples, desc=f"Group {group_id}", position=group_id):
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
                    "model": "qwen3vl_base",
                    "gpu_pair": list(gpu_pair),
                    "generated_text": generated_text,
                    "ground_truth": sample.get("ground_truth", ""),
                    "inference_time": inference_time,
                    "image_path": sample["image_path"]
                })

                del inputs, outputs
                torch.cuda.empty_cache()

            except Exception as e:
                print(f"[Group {group_id}] ✗ {sample['id']} 失败: {e}")
                results.append({
                    "id": sample["id"],
                    "model": "qwen3vl_base",
                    "gpu_pair": list(gpu_pair),
                    "error": str(e)
                })
                torch.cuda.empty_cache()

        # 保存结果
        output_file = output_dir / f"base_group{group_id}.jsonl"
        with open(output_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        print(f"[Group {group_id}] ✓ 完成，结果: {output_file}")

    except Exception as e:
        print(f"[Group {group_id}] ✗✗ Worker失败: {e}")
        import traceback
        traceback.print_exc()

def merge_results(output_dir: Path, num_groups: int):
    """合并结果"""
    all_results = []

    for group_id in range(num_groups):
        result_file = output_dir / f"base_group{group_id}.jsonl"
        if result_file.exists():
            with open(result_file) as f:
                for line in f:
                    all_results.append(json.loads(line))

    all_results.sort(key=lambda x: x["id"])

    merged_file = output_dir / "qwen3vl_base_results.jsonl"
    with open(merged_file, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = [r for r in all_results if "error" not in r]
    failed = [r for r in all_results if "error" in r]

    stats = {
        "model": "qwen3vl_base",
        "mode": "8gpu_parallel",
        "total_samples": len(all_results),
        "success_count": len(success),
        "failed_count": len(failed),
        "success_rate": len(success) / len(all_results) if all_results else 0,
        "avg_inference_time": float(np.mean([r["inference_time"] for r in success])) if success else 0,
        "total_time": sum([r["inference_time"] for r in success]),
    }

    stats_file = output_dir / "qwen3vl_base_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("8卡并行基础模型推理完成")
    print(f"{'='*60}")
    print(f"总样本数: {stats['total_samples']}")
    print(f"成功: {stats['success_count']} | 失败: {stats['failed_count']}")
    print(f"成功率: {stats['success_rate']:.2%}")
    print(f"平均推理时间: {stats['avg_inference_time']:.2f}s")
    print(f"总推理时间: {stats['total_time']:.1f}s ({stats['total_time']/60:.1f}min)")
    print(f"{'='*60}\n")

def main():
    parser = argparse.ArgumentParser(description="8卡并行基础模型推理")
    parser.add_argument("--model", type=str, default="/app/models/qwen3-vl-8b-instruct")
    parser.add_argument("--dataset", type=str, default="/app/dataset_index_100.json")
    parser.add_argument("--prompt", type=str, default="/app/prompt.txt")
    parser.add_argument("--output-dir", type=str, default="/app/outputs")
    parser.add_argument("--gpu-pairs", type=str, default="0,1;2,3;4,5;6,7")
    args = parser.parse_args()

    # 解析GPU对
    gpu_pairs = []
    for pair_str in args.gpu_pairs.split(";"):
        gpus = tuple(map(int, pair_str.split(",")))
        gpu_pairs.append(gpus)

    with open(args.dataset) as f:
        samples = json.load(f)

    with open(args.prompt) as f:
        prompt_text = f.read().strip()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    num_groups = len(gpu_pairs)
    print(f"\n8卡并行基础模型推理 (无LoRA)")
    print(f"GPU对: {gpu_pairs}")
    print(f"样本总数: {len(samples)}")
    print(f"每组样本数: ~{len(samples) // num_groups}\n")

    sample_splits = split_dataset(samples, num_groups)

    processes = []
    for i, gpu_pair in enumerate(gpu_pairs):
        p = mp.Process(
            target=inference_worker,
            args=(gpu_pair, i, args.model,
                  sample_splits[i], prompt_text, output_dir)
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    merge_results(output_dir, num_groups)

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    main()
