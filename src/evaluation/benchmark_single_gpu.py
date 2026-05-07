#!/usr/bin/env python3
"""
FinMME Benchmark - 单GPU顺序推理脚本
针对LoRA模型加载的内存优化版本
"""
import os
import sys
import json
import time
import argparse
import torch
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
from PIL import Image

# 基础配置
BASE_MODEL = "$MODEL_ROOT/qwen3-vl-8b-instruct"
DATA_BASE = "/data/finmme-bench/data"
OUTPUT_BASE = "/data/finmme-bench/outputs/full_1000"

# 模型配置：3个最佳checkpoint
MODELS = {
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

# 像素限制
PIXEL_LIMITS = {
    "max_pixels": 1280 * 32 * 32,
    "min_pixels": 256 * 32 * 32,
}


def get_all_samples() -> List[Dict]:
    """获取所有样本"""
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


def run_inference(
    model_name: str,
    model_config: Dict,
    samples: List[Dict],
    prompt_cn: str,
    prompt_en: str,
    output_dir: Path,
    gpu_id: int = 0
):
    """运行单模型推理"""
    from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
    from peft import PeftModel

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
    print(f"GPU: {gpu_id}")
    print(f"总样本: {len(samples)} | 已完成: {len(completed_ids)} | 待推理: {len(pending_samples)}")
    print(f"{'='*60}")

    if not pending_samples:
        print("所有样本已完成！")
        return

    # 设置GPU
    device = f"cuda:{gpu_id}"
    torch.cuda.set_device(gpu_id)

    # 清理GPU内存
    torch.cuda.empty_cache()

    # 加载处理器
    processor = AutoProcessor.from_pretrained(
        BASE_MODEL,
        max_pixels=PIXEL_LIMITS["max_pixels"],
        min_pixels=PIXEL_LIMITS["min_pixels"],
    )

    # 加载模型
    print("加载基础模型...")
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map=device,
        attn_implementation="sdpa",
    )

    # 加载LoRA
    lora_path = model_config.get("lora_path")
    if lora_path:
        print(f"加载LoRA: {lora_path}")
        model = PeftModel.from_pretrained(model, lora_path)
        model = model.merge_and_unload()

    model.eval()
    print("模型加载完成！")

    # 推理
    for sample in tqdm(pending_samples, desc=f"{model_name} 推理"):
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

        # 实时保存
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    # 清理
    del model
    torch.cuda.empty_cache()

    print(f"✓ {model_name} 完成")


def main():
    parser = argparse.ArgumentParser(description="FinMME 单GPU推理")
    parser.add_argument("--model", type=str, required=True, choices=list(MODELS.keys()))
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--prompt-cn", type=str, default="/data/finmme-bench/prompt.txt")
    parser.add_argument("--prompt-en", type=str, default="/data/finmme-bench/prompt_en.txt")
    parser.add_argument("--output-dir", type=str, default=OUTPUT_BASE)
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

    # 运行推理
    run_inference(
        model_name=args.model,
        model_config=MODELS[args.model],
        samples=samples,
        prompt_cn=prompt_cn,
        prompt_en=prompt_en,
        output_dir=output_dir,
        gpu_id=args.gpu
    )


if __name__ == "__main__":
    main()
