#!/usr/bin/env python3
"""
基础模型 8卡并行推理脚本
支持: Qwen2.5-VL-7B, Qwen3-VL-2B, Qwen3-VL-4B, Qwen3-VL-8B

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

# 统一的像素限制配置
# Qwen2.5-VL 使用 patch_size=14, Qwen3-VL 使用 patch_size=16
# 为了公平对比，统一使用 ~1M pixels 的限制
PIXEL_LIMITS = {
    "qwen25": {
        "max_pixels": 1280 * 28 * 28,  # ~1,003,520 pixels
        "min_pixels": 256 * 28 * 28,   # ~200,704 pixels
    },
    "qwen3": {
        "max_pixels": 1280 * 32 * 32,  # ~1,310,720 pixels
        "min_pixels": 256 * 32 * 32,   # ~262,144 pixels
    }
}

# 模型配置
MODELS = {
    "qwen25vl-7b": {
        "path": "$MODEL_ROOT/Qwen2___5-VL-7B-Instruct",
        "type": "qwen25"
    },
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
    """单GPU推理worker"""
    try:
        os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)

        print(f"[GPU {gpu_id}] 启动，样本数: {len(samples)}")

        if model_type == "qwen3":
            from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
            model_class = Qwen3VLForConditionalGeneration
        else:  # qwen25
            from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
            model_class = Qwen2_5_VLForConditionalGeneration

        # 加载模型
        print(f"[GPU {gpu_id}] 加载模型 {model_name}...")
        model = model_class.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="cuda:0",
            attn_implementation="eager"
        )

        processor = AutoProcessor.from_pretrained(model_path)

        # 设置 max_pixels 限制，避免大图片 OOM
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
    parser = argparse.ArgumentParser(description="基础模型8卡并行推理")
    parser.add_argument("--model", type=str, required=True, choices=list(MODELS.keys()),
                        help="模型名称: qwen25vl-7b, qwen3vl-2b, qwen3vl-4b, qwen3vl-8b")
    parser.add_argument("--dataset", type=str, default="/data/finmme-bench/dataset_index_485.json")
    parser.add_argument("--prompt", type=str, default="/data/finmme-bench/prompt.txt")
    parser.add_argument("--output-dir", type=str, default="/data/finmme-bench/outputs")
    parser.add_argument("--num-gpus", type=int, default=8)
    args = parser.parse_args()

    model_config = MODELS[args.model]
    model_path = model_config["path"]
    model_type = model_config["type"]
    model_name = args.model

    with open(args.dataset) as f:
        samples = json.load(f)

    with open(args.prompt) as f:
        prompt_text = f.read().strip()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    num_gpus = args.num_gpus
    print(f"\n{'='*60}")
    print(f"{model_name} 8卡并行推理")
    print(f"{'='*60}")
    print(f"模型路径: {model_path}")
    print(f"样本总数: {len(samples)}")
    print(f"每GPU样本数: ~{len(samples) // num_gpus}")
    print(f"{'='*60}\n")

    sample_splits = split_dataset(samples, num_gpus)

    processes = []
    for gpu_id in range(num_gpus):
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
