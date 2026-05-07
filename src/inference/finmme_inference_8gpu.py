#!/usr/bin/env python3
"""
FinMME 官方 Benchmark 推理脚本 - 8卡并行
支持: Qwen3-VL-8B base 和 LoRA (SFT) 模型
评估: single_choice / multiple_choice / numerical
"""
import os
os.environ['NCCL_P2P_DISABLE'] = '1'
os.environ['NCCL_IB_DISABLE'] = '1'

import torch
import json
import re
import argparse
import multiprocessing as mp
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm

# Qwen3-VL 像素限制
MAX_PIXELS = 1280 * 32 * 32  # ~1,310,720
MIN_PIXELS = 256 * 32 * 32   # ~262,144


# ============================================================
# FinMME 官方 Prompt 模板
# ============================================================

PROMPT_TEMPLATES = {
    "single_choice": (
        "Please answer this single choice question about the image. "
        "The caption of the image is {verified_caption}. "
        "The related sentences are {related_sentences}.\n"
        "Please answer the question directly. The answer MUST be of the following format: "
        "'Answer: $ANSWER' (without quotes) where $ANSWER is the answer to the problem "
        "(the single letter of the correct answer, A, B, C, D, etc.).\n"
        "Question: {question_text}\n"
        "Options: {options}"
    ),
    "multiple_choice": (
        "Please answer this multiple choice question about the image. "
        "The caption of the image is {verified_caption}. "
        "The related sentences are {related_sentences}.\n"
        "Please answer the question directly. The answer MUST be of the following format: "
        "'Answer: $ANSWER' (without quotes) where $ANSWER is the answer to the problem "
        "(the letter(s) of the correct answer(s), split by ',').\n"
        "Question: {question_text}\n"
        "Options: {options}"
    ),
    "numerical": (
        "Please answer this numerical question about the image. "
        "The unit of the answer is {unit}. "
        "The caption of the image is {verified_caption}. "
        "The related sentences are {related_sentences}.\n"
        "Please answer the question directly. The answer MUST be of the following format: "
        "'Answer: $ANSWER' (without quotes) where $ANSWER is the answer to the problem "
        "(digit number only, without unit or any other text).\n"
        "Question: {question_text}"
    ),
}


def build_prompt(sample: Dict) -> str:
    """根据题目类型构建 prompt"""
    qt = sample["question_type"]
    template = PROMPT_TEMPLATES[qt]
    return template.format(
        verified_caption=sample.get("verified_caption", ""),
        related_sentences=sample.get("related_sentences", ""),
        question_text=sample["question_text"],
        options=sample.get("options", ""),
        unit=sample.get("unit", ""),
    )


# ============================================================
# 答案提取与评估 (官方逻辑)
# ============================================================

def normalize_answer(text: str) -> str:
    """清理 LaTeX 等格式"""
    text = text.replace("**", "").replace("$\\boxed{", "").replace("}$", "")
    text = text.replace("\\$", "").strip()
    return text


def extract_answer(response: str) -> str:
    """从模型输出中提取答案"""
    # 去除可能的 <think>...</think> 块
    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    response = normalize_answer(response)
    # 官方正则
    match = re.search(r"(?i)Answer\s*:\s*([^\s\n]+)", response)
    if match:
        return match.group(1).strip()
    return ""


def extract_choice_letters(text: str) -> set:
    """提取选择题字母"""
    return set(re.findall(r"[A-N]", text.upper()))


def extract_number(text: str) -> Optional[float]:
    """提取数值"""
    text = text.replace(",", "").replace("%", "").strip()
    match = re.search(r"-?[\d]+\.?[\d]*", text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def evaluate_single(sample: Dict, response: str) -> Dict:
    """评估单个样本"""
    qt = sample["question_type"]
    answer = extract_answer(response)
    gt = sample["answer"]

    result = {
        "id": sample["id"],
        "question_type": qt,
        "ground_truth": gt,
        "extracted_answer": answer,
        "raw_response": response,
    }

    if qt == "single_choice":
        pred_letters = extract_choice_letters(answer)
        gt_letters = extract_choice_letters(gt)
        # 单选: 精确匹配
        result["correct"] = pred_letters == gt_letters and len(pred_letters) == 1
        result["score"] = 1.0 if result["correct"] else 0.0

    elif qt == "multiple_choice":
        pred_letters = extract_choice_letters(answer)
        gt_letters = extract_choice_letters(gt)
        n = len(gt_letters)
        if n == 0:
            result["correct"] = False
            result["score"] = 0.0
        else:
            c = len(pred_letters & gt_letters)         # 正确选中
            i = len(pred_letters - gt_letters)          # 错误选中
            s = len(pred_letters) if pred_letters else 1
            score = max(0, c / n - i / s)
            result["correct"] = pred_letters == gt_letters
            result["score"] = score
            result["hallucination"] = i / s if s > 0 else 0

    elif qt == "numerical":
        pred_num = extract_number(answer)
        gt_num = extract_number(gt)
        tolerance = sample.get("tolerance")
        if pred_num is not None and gt_num is not None:
            if tolerance is not None and tolerance > 0:
                result["correct"] = abs(pred_num - gt_num) <= tolerance
            else:
                result["correct"] = abs(pred_num - gt_num) < 1e-6
        else:
            result["correct"] = False
        result["score"] = 1.0 if result["correct"] else 0.0

    return result


# ============================================================
# 推理 Worker
# ============================================================

def split_dataset(samples: List[Dict], n: int) -> List[List[Dict]]:
    """均匀分片"""
    size = len(samples) // n
    rem = len(samples) % n
    splits, start = [], 0
    for i in range(n):
        end = start + size + (1 if i < rem else 0)
        splits.append(samples[start:end])
        start = end
    return splits


def inference_worker(
    gpu_id: int,
    model_path: str,
    lora_path: Optional[str],
    model_name: str,
    samples: List[Dict],
    output_dir: Path,
    sft_lora_path: Optional[str] = None,
):
    """单 GPU 推理 worker

    支持三种加载模式:
    1. base only: model_path (无 lora)
    2. base + SFT: model_path + lora_path (单层 merge)
    3. base + SFT + DPO/FCPO: model_path + sft_lora_path + lora_path (双层 merge)
    """
    try:
        os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)
        print(f"[GPU {gpu_id}] 启动, 样本数: {len(samples)}, model: {model_name}")

        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
        from PIL import Image
        import gc

        # 加载基座模型
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="cuda:0",
            attn_implementation="eager",
        )

        # 双层 merge: base → SFT → DPO/FCPO
        if sft_lora_path and lora_path:
            from peft import PeftModel
            print(f"[GPU {gpu_id}] 合并 SFT LoRA: {sft_lora_path}")
            model = PeftModel.from_pretrained(model, sft_lora_path)
            model = model.merge_and_unload()
            gc.collect(); torch.cuda.empty_cache()
            print(f"[GPU {gpu_id}] 合并 DPO/FCPO LoRA: {lora_path}")
            model = PeftModel.from_pretrained(model, lora_path)
            model = model.merge_and_unload()
            gc.collect(); torch.cuda.empty_cache()
        # 单层 merge: base → SFT
        elif lora_path:
            from peft import PeftModel
            print(f"[GPU {gpu_id}] 加载 LoRA: {lora_path}")
            model = PeftModel.from_pretrained(model, lora_path)
            model = model.merge_and_unload()

        processor = AutoProcessor.from_pretrained(model_path)
        processor.image_processor.max_pixels = MAX_PIXELS
        processor.image_processor.min_pixels = MIN_PIXELS

        mem = torch.cuda.memory_allocated(0) / 1024**3
        print(f"[GPU {gpu_id}] 显存: {mem:.2f} GB")

        results = []
        for sample in tqdm(samples, desc=f"GPU {gpu_id}", position=gpu_id):
            try:
                image = Image.open(sample["image_path"]).convert("RGB")
                prompt = build_prompt(sample)

                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ]
                text_prompt = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True,
                    enable_thinking=False,  # 关闭 thinking mode
                )
                inputs = processor(
                    text=[text_prompt], images=[image], return_tensors="pt"
                ).to(model.device)

                t0 = time.time()
                with torch.no_grad():
                    outputs = model.generate(
                        **inputs,
                        max_new_tokens=512,
                        do_sample=False,
                        # Qwen3-VL 默认开启 thinking, 关闭以加速
                        # 如果报错就去掉这行
                    )
                dt = time.time() - t0

                generated = processor.decode(
                    outputs[0][inputs["input_ids"].shape[1]:],
                    skip_special_tokens=True,
                )

                eval_result = evaluate_single(sample, generated)
                eval_result.update({
                    "model": model_name,
                    "gpu_id": gpu_id,
                    "inference_time": dt,
                    "image_path": sample["image_path"],
                })
                results.append(eval_result)

                del inputs, outputs
                torch.cuda.empty_cache()

            except Exception as e:
                print(f"[GPU {gpu_id}] ✗ id={sample['id']}: {e}")
                results.append({
                    "id": sample["id"],
                    "model": model_name,
                    "question_type": sample["question_type"],
                    "error": str(e),
                })
                torch.cuda.empty_cache()

        # 保存分片结果
        out_file = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        with open(out_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[GPU {gpu_id}] ✓ 完成, 保存到 {out_file}")

    except Exception as e:
        print(f"[GPU {gpu_id}] ✗✗ Worker 失败: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# 合并 & 评估
# ============================================================

def merge_and_evaluate(output_dir: Path, model_name: str, num_gpus: int):
    """合并分片结果并计算最终指标"""
    all_results = []
    for gpu_id in range(num_gpus):
        f = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        if f.exists():
            with open(f) as fh:
                for line in fh:
                    all_results.append(json.loads(line))

    all_results.sort(key=lambda x: x["id"])

    # 保存合并结果
    merged_file = output_dir / f"{model_name}_results.jsonl"
    with open(merged_file, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 分类统计
    success = [r for r in all_results if "error" not in r]
    failed = [r for r in all_results if "error" in r]

    type_stats = {}
    for r in success:
        qt = r["question_type"]
        if qt not in type_stats:
            type_stats[qt] = {"correct": 0, "total": 0, "scores": []}
        type_stats[qt]["total"] += 1
        type_stats[qt]["scores"].append(r.get("score", 0))
        if r.get("correct"):
            type_stats[qt]["correct"] += 1

    # 整体准确率
    total_correct = sum(v["correct"] for v in type_stats.values())
    total_count = sum(v["total"] for v in type_stats.values())
    overall_acc = total_correct / total_count if total_count > 0 else 0

    # 各类型准确率
    type_acc = {}
    for qt, stats in type_stats.items():
        type_acc[qt] = {
            "accuracy": stats["correct"] / stats["total"] if stats["total"] > 0 else 0,
            "avg_score": float(np.mean(stats["scores"])) if stats["scores"] else 0,
            "correct": stats["correct"],
            "total": stats["total"],
        }

    # 多选题 hallucination rate
    mc_results = [r for r in success if r["question_type"] == "multiple_choice"]
    hallucination_rate = 0
    if mc_results:
        h_rates = [r.get("hallucination", 0) for r in mc_results]
        hallucination_rate = float(np.mean(h_rates))

    # FinScore 简化版 (无 knowledge_domain)
    avg_score = float(np.mean([r.get("score", 0) for r in success])) if success else 0
    finscore = avg_score * (1 - hallucination_rate)

    summary = {
        "model": model_name,
        "total_samples": len(all_results),
        "success": len(success),
        "failed": len(failed),
        "overall_accuracy": overall_acc,
        "overall_avg_score": avg_score,
        "hallucination_rate": hallucination_rate,
        "finscore": finscore,
        "by_type": type_acc,
        "avg_inference_time": float(np.mean([r.get("inference_time", 0) for r in success])) if success else 0,
    }

    summary_file = output_dir / f"{model_name}_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 打印报告
    print(f"\n{'='*60}")
    print(f"  FinMME Benchmark Results: {model_name}")
    print(f"{'='*60}")
    print(f"  Total: {len(all_results)} | Success: {len(success)} | Failed: {len(failed)}")
    print(f"  Overall Accuracy:  {overall_acc:.4f} ({total_correct}/{total_count})")
    print(f"  Overall Avg Score: {avg_score:.4f}")
    print(f"  Hallucination Rate: {hallucination_rate:.4f}")
    print(f"  FinScore:          {finscore:.4f}")
    print(f"  Avg Inference Time: {summary['avg_inference_time']:.2f}s")
    print(f"\n  By Question Type:")
    for qt, acc in sorted(type_acc.items()):
        print(f"    {qt:20s}: acc={acc['accuracy']:.4f} score={acc['avg_score']:.4f} ({acc['correct']}/{acc['total']})")
    print(f"{'='*60}\n")

    # 清理分片文件
    for gpu_id in range(num_gpus):
        tmp = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        if tmp.exists():
            tmp.unlink()

    return summary


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="FinMME 8卡并行推理")
    parser.add_argument("--model-path", type=str, required=True,
                        help="基座模型路径")
    parser.add_argument("--lora-path", type=str, default=None,
                        help="LoRA adapter 路径 (不指定则用 base)")
    parser.add_argument("--sft-lora-path", type=str, default=None,
                        help="SFT LoRA 路径 (用于双层 merge: base→SFT→DPO)")
    parser.add_argument("--model-name", type=str, required=True,
                        help="模型标识 (如 qwen3vl_base, qwen3vl_sft)")
    parser.add_argument("--dataset", type=str, required=True,
                        help="数据集 JSON 路径")
    parser.add_argument("--output-dir", type=str, default="./finmme_results")
    parser.add_argument("--num-gpus", type=int, default=8)
    args = parser.parse_args()

    with open(args.dataset) as f:
        samples = json.load(f)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  FinMME Benchmark Inference")
    print(f"{'='*60}")
    print(f"  Model: {args.model_name}")
    print(f"  Base:  {args.model_path}")
    print(f"  SFT:   {args.sft_lora_path or 'N/A'}")
    print(f"  LoRA:  {args.lora_path or 'None (base model)'}")
    print(f"  Samples: {len(samples)}")
    print(f"  GPUs: {args.num_gpus}")
    print(f"{'='*60}\n")

    splits = split_dataset(samples, args.num_gpus)

    processes = []
    for gpu_id in range(args.num_gpus):
        p = mp.Process(
            target=inference_worker,
            args=(gpu_id, args.model_path, args.lora_path,
                  args.model_name, splits[gpu_id], output_dir,
                  args.sft_lora_path),
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    merge_and_evaluate(output_dir, args.model_name, args.num_gpus)


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()
