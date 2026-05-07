#!/usr/bin/env python3
"""
增量推理脚本 - 8卡并行推理新增样本
支持: qwen3vl-2b, qwen3vl-4b, qwen3vl-8b, exp-002, exp-005
严格参考 base_model_inference.py 配置
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

# 统一的像素限制配置 - 与 base_model_inference.py 一致
PIXEL_LIMITS = {
    "qwen3": {
        "max_pixels": 1280 * 32 * 32,  # ~1,310,720 pixels
        "min_pixels": 256 * 32 * 32,   # ~262,144 pixels
    }
}

# 模型配置 - 只包含 qwen3 系列，排除 qwen25vl-7b
MODELS = {
    "qwen3vl-2b": {
        "path": "$MODEL_ROOT/Qwen3-VL-2B-Instruct/Qwen/Qwen3-VL-2B-Instruct",
        "type": "qwen3"
    },
    "qwen3vl-4b": {
        "path": "$MODEL_ROOT/Qwen/Qwen3-VL-4B-Instruct",
        "type": "qwen3"
    },
    "qwen3vl-8b": {
        "path": "$MODEL_ROOT/qwen3-vl-8b-instruct",
        "type": "qwen3"
    },
    "exp-002": {
        "path": "$DATA_ROOT/sft/outputs/exp-002/merged_model",
        "type": "qwen3"
    },
    "exp-005": {
        "path": "$DATA_ROOT/sft/outputs/exp-005/merged_model",
        "type": "qwen3"
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
    model_path: str,
    model_type: str,
    model_name: str,
    samples: List[Dict],
    prompt_text: str,
    output_dir: Path
):
    """单GPU推理worker - 与 base_model_inference.py 一致"""
    try:
        os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)

        print(f"[GPU {gpu_id}] 启动，样本数: {len(samples)}")

        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
        model_class = Qwen3VLForConditionalGeneration

        # 加载模型
        print(f"[GPU {gpu_id}] 加载模型 {model_name}...")
        model = model_class.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="cuda:0",
            attn_implementation="eager"
        )

        processor = AutoProcessor.from_pretrained(model_path)

        # 设置 max_pixels 限制 - 与 base_model_inference.py 一致
        pixel_config = PIXEL_LIMITS[model_type]
        processor.image_processor.size = {
            "longest_edge": pixel_config["max_pixels"],
            "shortest_edge": pixel_config["min_pixels"]
        }
        processor.image_processor.max_pixels = pixel_config["max_pixels"]
        processor.image_processor.min_pixels = pixel_config["min_pixels"]
        print(f"[GPU {gpu_id}] max_pixels: {pixel_config['max_pixels']:,}")

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
        output_file = output_dir / f"{model_name}_incr_gpu{gpu_id}.jsonl"
        with open(output_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        print(f"[GPU {gpu_id}] ✓ 完成，结果: {output_file}")

    except Exception as e:
        print(f"[GPU {gpu_id}] ✗✗ Worker失败: {e}")
        import traceback
        traceback.print_exc()


def merge_results(output_dir: Path, model_name: str, num_gpus: int):
    """合并增量结果到主结果文件"""
    # 收集增量结果
    incr_results = []
    for gpu_id in range(num_gpus):
        result_file = output_dir / f"{model_name}_incr_gpu{gpu_id}.jsonl"
        if result_file.exists():
            with open(result_file) as f:
                for line in f:
                    incr_results.append(json.loads(line))

    incr_results.sort(key=lambda x: x["id"])

    # 加载已有结果
    main_file = output_dir / f"{model_name}_results.jsonl"
    existing_results = []
    if main_file.exists():
        with open(main_file) as f:
            for line in f:
                existing_results.append(json.loads(line))

    # 合并
    all_results = existing_results + incr_results
    all_results.sort(key=lambda x: x["id"])

    # 保存合并结果
    with open(main_file, "w", encoding="utf-8") as f:
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
        source_stats[source]["total_time"] += r.get("inference_time", 0)

    stats = {
        "model": model_name,
        "mode": f"{num_gpus}gpu_parallel",
        "total_samples": len(all_results),
        "existing_samples": len(existing_results),
        "incremental_samples": len(incr_results),
        "success_count": len(success),
        "failed_count": len(failed),
        "success_rate": len(success) / len(all_results) if all_results else 0,
        "avg_inference_time": float(np.mean([r.get("inference_time", 0) for r in success])) if success else 0,
        "source_breakdown": {
            k: {"count": v["count"], "avg_time": v["total_time"] / v["count"] if v["count"] > 0 else 0}
            for k, v in source_stats.items()
        }
    }

    stats_file = output_dir / f"{model_name}_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"{model_name} 增量推理完成")
    print(f"{'='*60}")
    print(f"已有样本: {stats['existing_samples']}")
    print(f"新增样本: {stats['incremental_samples']}")
    print(f"合并后总数: {stats['total_samples']}")
    print(f"成功: {stats['success_count']} | 失败: {stats['failed_count']}")
    print(f"成功率: {stats['success_rate']:.2%}")
    print(f"\n按来源统计:")
    for source, data in stats["source_breakdown"].items():
        print(f"  {source}: {data['count']}个, 平均{data['avg_time']:.2f}s")
    print(f"{'='*60}\n")

    # 清理临时文件
    for gpu_id in range(num_gpus):
        tmp_file = output_dir / f"{model_name}_incr_gpu{gpu_id}.jsonl"
        if tmp_file.exists():
            tmp_file.unlink()


def main():
    parser = argparse.ArgumentParser(description="增量推理脚本")
    parser.add_argument("--model", type=str, required=True, choices=list(MODELS.keys()),
                        help="模型名称")
    parser.add_argument("--prompt", type=str, default="/data/finmme-bench/prompt.txt")
    parser.add_argument("--output-dir", type=str, default="/data/finmme-bench/outputs")
    parser.add_argument("--num-gpus", type=int, default=8)
    args = parser.parse_args()

    model_config = MODELS[args.model]
    model_path = model_config["path"]
    model_type = model_config["type"]
    model_name = args.model

    output_dir = Path(args.output_dir)

    # 加载增量样本
    incr_file = output_dir / f"{model_name}_incremental.json"
    if not incr_file.exists():
        print(f"增量样本文件不存在: {incr_file}")
        return

    with open(incr_file) as f:
        samples = json.load(f)

    if len(samples) == 0:
        print("无新增样本需要推理")
        return

    with open(args.prompt) as f:
        prompt_text = f.read().strip()

    num_gpus = args.num_gpus
    print(f"\n{'='*60}")
    print(f"{model_name} 增量推理 (8卡并行)")
    print(f"{'='*60}")
    print(f"模型路径: {model_path}")
    print(f"新增样本数: {len(samples)}")
    print(f"每GPU样本数: ~{len(samples) // num_gpus}")
    print(f"{'='*60}\n")

    sample_splits = split_dataset(samples, num_gpus)

    processes = []
    for gpu_id in range(num_gpus):
        if len(sample_splits[gpu_id]) == 0:
            continue
        p = mp.Process(
            target=inference_worker,
            args=(gpu_id, model_path, model_type, model_name,
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
