#!/usr/bin/env python3
"""
LoRA模型推理脚本 - 使用 PEFT 加载 LoRA adapter
支持 Qwen3-VL-8B + LoRA SFT 模型
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
import numpy as np

def main():
    parser = argparse.ArgumentParser(description="LoRA模型推理")
    parser.add_argument(
        "--base-model",
        type=str,
        default="$MODEL_ROOT/qwen3-vl-8b-instruct",
        help="基础模型路径"
    )
    parser.add_argument(
        "--lora-path",
        type=str,
        default="$DATA_ROOT/sft/outputs/qwen3vl_chart_lora_v3",
        help="LoRA adapter路径"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="dataset_index.json",
        help="数据集索引文件"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="prompt.txt",
        help="提示词文件"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="输出目录"
    )
    parser.add_argument(
        "--gpu",
        type=str,
        default="0,1",
        help="使用的GPU (默认: 0,1 双卡)"
    )
    args = parser.parse_args()

    # 设置GPU
    os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu

    print(f"\n{'='*60}")
    print("LoRA 模型推理")
    print(f"{'='*60}")
    print(f"基础模型: {args.base_model}")
    print(f"LoRA adapter: {args.lora_path}")
    print(f"GPU: {args.gpu}")
    print(f"{'='*60}\n")

    # 动态导入
    from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
    from peft import PeftModel, PeftConfig

    # 读取数据集
    with open(args.dataset) as f:
        samples = json.load(f)

    # 读取提示词
    with open(args.prompt) as f:
        prompt_text = f.read().strip()

    print(f"样本数: {len(samples)}")
    print(f"提示词: {prompt_text[:100]}...")

    # 加载基础模型
    print("\n加载基础模型...")
    base_model = Qwen3VLForConditionalGeneration.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="eager"
    )

    # 加载 LoRA adapter
    print(f"加载 LoRA adapter: {args.lora_path}")
    model = PeftModel.from_pretrained(base_model, args.lora_path)
    model = model.merge_and_unload()  # 合并 LoRA 权重以加速推理
    print("✓ LoRA adapter 已加载并合并")

    # 加载 processor
    processor = AutoProcessor.from_pretrained(args.base_model)

    # 打印显存使用
    for i in range(torch.cuda.device_count()):
        mem = torch.cuda.memory_allocated(i) / 1024**3
        print(f"GPU {i} 显存: {mem:.2f} GB")

    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    results = []

    # 推理循环
    print(f"\n开始推理 {len(samples)} 个样本...")
    for sample in tqdm(samples, desc="推理进度"):
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
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            inputs = processor(
                text=[text_prompt],
                images=[image],
                return_tensors="pt"
            ).to(model.device)

            start_time = time.time()
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=2048,
                    do_sample=False
                )
            inference_time = time.time() - start_time

            generated_text = processor.decode(
                outputs[0][inputs['input_ids'].shape[1]:],
                skip_special_tokens=True
            )

            results.append({
                "id": sample["id"],
                "model": "qwen3vl_lora_v3",
                "generated_text": generated_text,
                "ground_truth": sample.get("ground_truth", ""),
                "inference_time": inference_time,
                "image_path": sample["image_path"]
            })

            # 清理显存
            del inputs, outputs
            torch.cuda.empty_cache()

        except Exception as e:
            print(f"\n✗ {sample['id']} 失败: {e}")
            results.append({
                "id": sample["id"],
                "model": "qwen3vl_lora_v3",
                "error": str(e)
            })
            torch.cuda.empty_cache()

    # 保存结果
    output_file = output_dir / "qwen3vl_lora_v3_results.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 统计
    success = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    stats = {
        "model": "qwen3vl_lora_v3",
        "lora_path": args.lora_path,
        "total_samples": len(results),
        "success_count": len(success),
        "failed_count": len(failed),
        "success_rate": len(success) / len(results) if results else 0,
        "avg_inference_time": float(np.mean([r["inference_time"] for r in success])) if success else 0,
        "total_time": sum([r["inference_time"] for r in success]),
        "avg_length": float(np.mean([len(r["generated_text"]) for r in success])) if success else 0
    }

    stats_file = output_dir / "qwen3vl_lora_v3_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("推理完成")
    print(f"{'='*60}")
    print(f"总样本数: {stats['total_samples']}")
    print(f"成功: {stats['success_count']} | 失败: {stats['failed_count']}")
    print(f"成功率: {stats['success_rate']:.2%}")
    print(f"平均推理时间: {stats['avg_inference_time']:.2f}s")
    print(f"总推理时间: {stats['total_time']:.1f}s ({stats['total_time']/60:.1f}min)")
    print(f"结果文件: {output_file}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
