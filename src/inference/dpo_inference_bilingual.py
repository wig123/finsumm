#!/usr/bin/env python3
"""
DPO 模型 5卡并行推理脚本 (双语版本 + SDPA)
- 中文样本 (sync_300_cn): 使用 prompt.txt
- 英文样本 (fin-chart_200, finmme_200, sync_300_en): 使用 prompt_en.txt
- 使用 SDPA (PyTorch 内置) 加速
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

# Qwen3-VL 像素限制配置
MAX_PIXELS = 1280 * 32 * 32
MIN_PIXELS = 256 * 32 * 32

# 语言映射
CHINESE_SOURCES = {"sync_300_cn"}
ENGLISH_SOURCES = {"fin-chart_200", "finmme_200", "sync_300_en"}

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
    prompt_cn: str,
    prompt_en: str,
    output_dir: Path,
    image_base_path: str
):
    """单GPU推理worker"""
    try:
        os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)

        print(f"[GPU {gpu_id}] 启动，样本数: {len(samples)}")

        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
        from peft import PeftModel

        # 加载基础模型 - 使用 SDPA (PyTorch 2.0+ 内置加速)
        print(f"[GPU {gpu_id}] 加载基础模型 (SDPA)...")
        base_model = Qwen3VLForConditionalGeneration.from_pretrained(
            base_model_path,
            torch_dtype=torch.bfloat16,
            device_map="cuda:0",
            attn_implementation="sdpa"
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
        cn_count = en_count = 0

        for sample in tqdm(samples, desc=f"GPU {gpu_id}", position=gpu_id):
            try:
                # 路径映射
                img_path = sample["image_path"]
                if "/finmme-benchmark/data" in img_path:
                    img_path = image_base_path + "/" + "/".join(img_path.split("/finmme-benchmark/data/")[1:])

                image = Image.open(img_path).convert("RGB")

                # 根据来源选择提示词
                source = sample.get("source", "")
                if source in CHINESE_SOURCES:
                    prompt_text = prompt_cn
                    cn_count += 1
                else:
                    prompt_text = prompt_en
                    en_count += 1

                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": prompt_text}
                        ]
                    }
                ]

                text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = processor(
                    text=[text],
                    images=[image],
                    padding=True,
                    return_tensors="pt"
                ).to("cuda:0")

                start_time = time.time()
                with torch.no_grad():
                    generated_ids = model.generate(
                        **inputs,
                        max_new_tokens=2048,
                        do_sample=False,
                        temperature=None,
                        top_p=None,
                        top_k=None
                    )

                generated_ids_trimmed = [
                    out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
                ]
                output_text = processor.batch_decode(
                    generated_ids_trimmed,
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=False
                )[0]

                inference_time = time.time() - start_time

                results.append({
                    "id": sample["id"],
                    "source": source,
                    "lang": "cn" if source in CHINESE_SOURCES else "en",
                    "image_path": sample["image_path"],
                    "ground_truth": sample.get("ground_truth", ""),
                    "prediction": output_text,
                    "inference_time": inference_time,
                    "status": "success"
                })

            except Exception as e:
                results.append({
                    "id": sample["id"],
                    "source": sample.get("source", ""),
                    "image_path": sample["image_path"],
                    "ground_truth": sample.get("ground_truth", ""),
                    "prediction": "",
                    "error": str(e),
                    "status": "failed"
                })

        print(f"[GPU {gpu_id}] 完成: {len(results)} 样本 (中文: {cn_count}, 英文: {en_count})")

        # 保存中间结果
        tmp_file = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        with open(tmp_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    except Exception as e:
        print(f"[GPU {gpu_id}] 错误: {e}")
        import traceback
        traceback.print_exc()

def merge_results(output_dir: Path, model_name: str, num_gpus: int):
    """合并所有 GPU 结果"""
    all_results = []
    for gpu_id in range(num_gpus):
        tmp_file = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        if tmp_file.exists():
            with open(tmp_file) as f:
                for line in f:
                    all_results.append(json.loads(line))

    # 保存合并结果
    output_file = output_dir / f"{model_name}_results.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"合并结果: {len(all_results)} 样本 -> {output_file}")

    # 统计
    success = [r for r in all_results if r["status"] == "success"]
    failed = [r for r in all_results if r["status"] == "failed"]

    cn_samples = [r for r in success if r.get("lang") == "cn"]
    en_samples = [r for r in success if r.get("lang") == "en"]

    source_stats = {}
    for r in success:
        source = r["source"]
        if source not in source_stats:
            source_stats[source] = {"count": 0, "total_time": 0}
        source_stats[source]["count"] += 1
        source_stats[source]["total_time"] += r["inference_time"]

    stats = {
        "model": model_name,
        "mode": f"{num_gpus}gpu_parallel_sdpa",
        "total_samples": len(all_results),
        "success_count": len(success),
        "failed_count": len(failed),
        "cn_samples": len(cn_samples),
        "en_samples": len(en_samples),
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
    print(f"{model_name} 推理完成 (SDPA)")
    print(f"{'='*60}")
    print(f"总样本数: {stats['total_samples']}")
    print(f"成功: {stats['success_count']} | 失败: {stats['failed_count']}")
    print(f"中文样本: {stats['cn_samples']} | 英文样本: {stats['en_samples']}")
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
    parser = argparse.ArgumentParser(description="DPO模型5卡并行推理 (双语版本)")
    parser.add_argument("--model-name", type=str, default="dpo-exp002-ckpt85-bilingual", help="模型名称")
    parser.add_argument("--base-model", type=str,
                        default="<REMOTE_DATA_ROOT>/models/qwen3-vl-8b-instruct",
                        help="基础模型路径")
    parser.add_argument("--lora-path", type=str,
                        default="<REMOTE_DATA_ROOT>/qwen3vl-dpo/outputs/dpo-exp002/checkpoint-85",
                        help="LoRA checkpoint路径")
    parser.add_argument("--dataset", type=str,
                        default="<REMOTE_DATA_ROOT>/finmme-benchmark/dataset_index_1000_gt.json")
    parser.add_argument("--prompt-cn", type=str,
                        default="<REMOTE_DATA_ROOT>/finmme-benchmark/prompt.txt")
    parser.add_argument("--prompt-en", type=str,
                        default="<REMOTE_DATA_ROOT>/finmme-benchmark/prompt_en.txt")
    parser.add_argument("--output-dir", type=str,
                        default="<REMOTE_DATA_ROOT>/finmme-benchmark/outputs")
    parser.add_argument("--image-base", type=str,
                        default="<REMOTE_DATA_ROOT>/finmme-benchmark/data",
                        help="图片基础路径")
    parser.add_argument("--num-gpus", type=int, default=5)
    args = parser.parse_args()

    with open(args.dataset) as f:
        samples = json.load(f)

    with open(args.prompt_cn) as f:
        prompt_cn = f.read().strip()

    with open(args.prompt_en) as f:
        prompt_en = f.read().strip()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    # 统计语言分布
    cn_count = sum(1 for s in samples if s.get("source") in CHINESE_SOURCES)
    en_count = len(samples) - cn_count

    num_gpus = args.num_gpus
    print(f"\n{'='*60}")
    print(f"{args.model_name} DPO 5卡并行推理 (双语版本 + SDPA)")
    print(f"{'='*60}")
    print(f"基座模型: {args.base_model}")
    print(f"LoRA路径: {args.lora_path}")
    print(f"样本总数: {len(samples)} (中文: {cn_count}, 英文: {en_count})")
    print(f"每GPU样本数: ~{len(samples) // num_gpus}")
    print(f"{'='*60}\n")

    sample_splits = split_dataset(samples, num_gpus)

    processes = []
    for gpu_id in range(num_gpus):
        p = mp.Process(
            target=inference_worker,
            args=(gpu_id, args.base_model, args.lora_path, args.model_name,
                  sample_splits[gpu_id], prompt_cn, prompt_en, output_dir, args.image_base)
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    merge_results(output_dir, args.model_name, num_gpus)

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    main()
