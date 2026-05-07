#!/usr/bin/env python3
"""
ERNIE-4.5-VL-28B-A3B-Thinking 推理脚本
单进程多GPU模式，模型跨GPU加载
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

def run_inference(
    model_path: str,
    samples: list,
    prompt_text: str,
    output_dir: Path,
    gpus: list
):
    """使用 ERNIE-4.5-VL 进行推理"""

    # 设置可见GPU
    gpu_str = ",".join(map(str, gpus))
    os.environ['CUDA_VISIBLE_DEVICES'] = gpu_str

    print(f"\n{'='*60}")
    print(f"ERNIE-4.5-VL-28B-A3B-Thinking 推理")
    print(f"模型路径: {model_path}")
    print(f"GPU: {gpus}")
    print(f"样本数: {len(samples)}")
    print(f"{'='*60}\n")

    # 加载模型
    from transformers import AutoProcessor, AutoModelForCausalLM

    print("加载模型...")
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True
    )

    # 加载处理器
    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
    model.add_image_preprocess(processor)

    # 打印显存使用
    for i in range(len(gpus)):
        mem = torch.cuda.memory_allocated(i) / 1024**3
        print(f"cuda:{i} (GPU {gpus[i]}) 显存: {mem:.2f} GB")

    results = []
    total_time = 0
    success_count = 0

    # 推理循环
    for i, sample in enumerate(tqdm(samples, desc="ERNIE-4.5-VL")):
        try:
            print(f"[{i+1}/{len(samples)}] 处理 {sample['id']}...", end=" ")

            # 构建消息 - 使用image_url格式（官方示例）
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": sample['image_path']}},
                    ],
                },
            ]

            # 按官方示例处理
            text = processor.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            image_inputs, video_inputs = processor.process_vision_info(messages)
            inputs = processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )

            # 移动到设备
            device = next(model.parameters()).device
            inputs = inputs.to(device)

            # 推理 - 按官方示例
            start_time = time.time()
            with torch.no_grad():
                outputs = model.generate(
                    inputs=inputs['input_ids'].to(device),
                    **inputs,
                    max_new_tokens=2048,
                    use_cache=False
                )
            inference_time = time.time() - start_time
            total_time += inference_time

            # 解码
            generated_text = processor.decode(
                outputs[0][len(inputs['input_ids'][0]):],
                skip_special_tokens=True
            )

            results.append({
                "id": sample["id"],
                "model": "ernie-4.5-vl",
                "generated_text": generated_text,
                "ground_truth": sample["ground_truth"],
                "inference_time": inference_time,
                "image_path": sample["image_path"]
            })

            success_count += 1
            print(f"✓ {inference_time:.1f}s")

            # 清理显存
            del inputs, outputs
            torch.cuda.empty_cache()

        except Exception as e:
            print(f"✗ {str(e)[:50]}")
            results.append({
                "id": sample["id"],
                "model": "ernie-4.5-vl",
                "error": str(e)
            })
            torch.cuda.empty_cache()

    # 保存结果
    output_file = output_dir / "ernie_results.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 统计信息
    stats = {
        "model": "ernie-4.5-vl-28b",
        "total_samples": len(samples),
        "success_count": success_count,
        "failed_count": len(samples) - success_count,
        "success_rate": success_count / len(samples) if samples else 0,
        "total_time": total_time,
        "avg_inference_time": total_time / success_count if success_count else 0,
        "avg_length": np.mean([len(r["generated_text"]) for r in results if "generated_text" in r]) if success_count else 0
    }

    stats_file = output_dir / "ernie_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # 打印统计
    print(f"\n{'='*60}")
    print(f"ERNIE-4.5-VL 推理完成")
    print(f"{'='*60}")
    print(f"总样本数: {stats['total_samples']}")
    print(f"成功: {stats['success_count']} | 失败: {stats['failed_count']}")
    print(f"成功率: {stats['success_rate']:.2%}")
    print(f"平均推理时间: {stats['avg_inference_time']:.2f}s")
    print(f"总推理时间: {stats['total_time']:.1f}s ({stats['total_time']/60:.1f}min)")
    print(f"结果文件: {output_file}")
    print(f"{'='*60}\n")

    return results

def main():
    parser = argparse.ArgumentParser(description="ERNIE-4.5-VL 推理脚本")
    parser.add_argument(
        "--gpus",
        type=int,
        nargs="+",
        default=[0, 1, 2, 3, 4, 5, 6],
        help="使用的GPU ID列表"
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
        "--limit",
        type=int,
        default=None,
        help="限制处理样本数（用于测试）"
    )
    args = parser.parse_args()

    model_path = "$MODEL_ROOT/ERNIE-4.5-VL-28B-A3B-Thinking"

    # 读取数据集
    with open(args.dataset) as f:
        samples = json.load(f)

    if args.limit:
        samples = samples[:args.limit]

    # 读取提示词
    with open(args.prompt) as f:
        prompt_text = f.read()

    # 创建输出目录
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    # 运行推理
    run_inference(
        model_path=model_path,
        samples=samples,
        prompt_text=prompt_text,
        output_dir=output_dir,
        gpus=args.gpus
    )

if __name__ == "__main__":
    main()
