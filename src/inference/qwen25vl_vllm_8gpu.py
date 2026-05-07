#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen2.5-VL vLLM 8卡并行推理脚本
使用 vLLM 框架获得更好的输出质量
"""
import os
os.environ['NCCL_P2P_DISABLE'] = '1'
os.environ['NCCL_IB_DISABLE'] = '1'

import json
from pathlib import Path
from PIL import Image
import time
import argparse
import multiprocessing as mp
from typing import List, Dict
import numpy as np

# 模型配置
MODEL_PATH = "$MODEL_ROOT/Qwen2___5-VL-7B-Instruct"
MODEL_NAME = "qwen25vl-7b"

# 像素限制 (Qwen2.5-VL 使用 patch_size=14)
MIN_PIXELS = 256 * 28 * 28   # ~200,704 pixels
MAX_PIXELS = 1280 * 28 * 28  # ~1,003,520 pixels

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
    samples: List[Dict],
    prompt_text: str,
    output_dir: Path
):
    """单 GPU vLLM 推理 worker"""
    try:
        os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)

        print(f"[GPU {gpu_id}] 启动，样本数: {len(samples)}")

        from vllm import LLM, SamplingParams
        from transformers import AutoProcessor

        # 初始化 vLLM
        print(f"[GPU {gpu_id}] 加载 vLLM 模型...")
        llm = LLM(
            model=MODEL_PATH,
            trust_remote_code=True,
            gpu_memory_utilization=0.9,
            tensor_parallel_size=1,
            enforce_eager=True,
            max_model_len=4096,
            limit_mm_per_prompt={"image": 1},
        )

        # 加载 processor (使用 max_pixels 限制)
        processor = AutoProcessor.from_pretrained(
            MODEL_PATH,
            min_pixels=MIN_PIXELS,
            max_pixels=MAX_PIXELS
        )
        print(f"[GPU {gpu_id}] max_pixels: {MAX_PIXELS:,}")

        # 采样参数 - 贪婪解码
        sampling_params = SamplingParams(
            max_tokens=2048,
            temperature=0,
            top_p=1.0,
        )

        results = []

        for i, sample in enumerate(samples):
            try:
                # 加载图像
                image = Image.open(sample["image_path"]).convert("RGB")

                # 构建消息
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": prompt_text}
                        ]
                    }
                ]

                # 应用 chat template
                prompt = processor.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )

                # 构建输入
                llm_input = {
                    "prompt": prompt,
                    "multi_modal_data": {"image": image},
                }

                # 推理
                start_time = time.time()
                outputs = llm.generate([llm_input], sampling_params=sampling_params)
                inference_time = time.time() - start_time

                # 提取结果
                generated_text = outputs[0].outputs[0].text

                results.append({
                    "id": sample["id"],
                    "model": MODEL_NAME,
                    "gpu_id": gpu_id,
                    "framework": "vllm",
                    "generated_text": generated_text,
                    "ground_truth": sample.get("ground_truth", ""),
                    "inference_time": inference_time,
                    "image_path": sample["image_path"],
                    "source": sample.get("source", "")
                })

                if (i + 1) % 10 == 0:
                    print(f"[GPU {gpu_id}] 进度: {i+1}/{len(samples)}")

            except Exception as e:
                print(f"[GPU {gpu_id}] 错误 {sample['id']}: {str(e)[:50]}")
                results.append({
                    "id": sample["id"],
                    "model": MODEL_NAME,
                    "gpu_id": gpu_id,
                    "framework": "vllm",
                    "error": str(e),
                    "image_path": sample["image_path"],
                    "source": sample.get("source", "")
                })

        # 保存结果
        output_file = output_dir / f"{MODEL_NAME}_vllm_gpu{gpu_id}.jsonl"
        with open(output_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        print(f"[GPU {gpu_id}] 完成，结果: {output_file}")

    except Exception as e:
        print(f"[GPU {gpu_id}] Worker 失败: {e}")
        import traceback
        traceback.print_exc()


def merge_results(output_dir: Path, num_gpus: int):
    """合并结果"""
    all_results = []

    for gpu_id in range(num_gpus):
        result_file = output_dir / f"{MODEL_NAME}_vllm_gpu{gpu_id}.jsonl"
        if result_file.exists():
            with open(result_file) as f:
                for line in f:
                    all_results.append(json.loads(line))

    all_results.sort(key=lambda x: x["id"])

    merged_file = output_dir / f"{MODEL_NAME}_results.jsonl"
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
        "model": MODEL_NAME,
        "framework": "vllm",
        "mode": f"{num_gpus}gpu_parallel",
        "total_samples": len(all_results),
        "success_count": len(success),
        "failed_count": len(failed),
        "success_rate": len(success) / len(all_results) if all_results else 0,
        "avg_inference_time": float(np.mean([r["inference_time"] for r in success])) if success else 0,
        "total_time": sum([r["inference_time"] for r in success]),
        "avg_output_length": float(np.mean([len(r["generated_text"]) for r in success])) if success else 0,
        "source_breakdown": {
            k: {"count": v["count"], "avg_time": v["total_time"] / v["count"]}
            for k, v in source_stats.items()
        }
    }

    stats_file = output_dir / f"{MODEL_NAME}_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"{MODEL_NAME} vLLM 推理完成")
    print(f"{'='*60}")
    print(f"总样本数: {stats['total_samples']}")
    print(f"成功: {stats['success_count']} | 失败: {stats['failed_count']}")
    print(f"成功率: {stats['success_rate']:.2%}")
    print(f"平均推理时间: {stats['avg_inference_time']:.2f}s")
    print(f"平均输出长度: {stats['avg_output_length']:.0f} 字符")
    print(f"总推理时间: {stats['total_time']:.1f}s ({stats['total_time']/60:.1f}min)")
    print(f"\n按来源统计:")
    for source, data in stats["source_breakdown"].items():
        print(f"  {source}: {data['count']}个, 平均{data['avg_time']:.2f}s")
    print(f"{'='*60}\n")

    # 清理临时文件
    for gpu_id in range(num_gpus):
        tmp_file = output_dir / f"{MODEL_NAME}_vllm_gpu{gpu_id}.jsonl"
        if tmp_file.exists():
            tmp_file.unlink()


def main():
    parser = argparse.ArgumentParser(description="Qwen2.5-VL vLLM 8卡并行推理")
    parser.add_argument("--dataset", type=str, default="/data/finmme-bench/dataset_index_485.json")
    parser.add_argument("--prompt", type=str, default="/data/finmme-bench/prompt.txt")
    parser.add_argument("--output-dir", type=str, default="/data/finmme-bench/outputs")
    parser.add_argument("--num-gpus", type=int, default=8)
    args = parser.parse_args()

    with open(args.dataset) as f:
        samples = json.load(f)

    with open(args.prompt) as f:
        prompt_text = f.read().strip()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    num_gpus = args.num_gpus
    print(f"\n{'='*60}")
    print(f"{MODEL_NAME} vLLM 8卡并行推理")
    print(f"{'='*60}")
    print(f"模型路径: {MODEL_PATH}")
    print(f"max_pixels: {MAX_PIXELS:,}")
    print(f"样本总数: {len(samples)}")
    print(f"每GPU样本数: ~{len(samples) // num_gpus}")
    print(f"{'='*60}\n")

    sample_splits = split_dataset(samples, num_gpus)

    processes = []
    for gpu_id in range(num_gpus):
        p = mp.Process(
            target=inference_worker,
            args=(gpu_id, sample_splits[gpu_id], prompt_text, output_dir)
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    merge_results(output_dir, num_gpus)


if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    main()
