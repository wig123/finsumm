#!/usr/bin/env python3
"""
完整评估脚本 - 计算所有指标
BLEU | ROUGE-1 | ROUGE-L | CIDEr | METEOR | FactScore v2 | Judge
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
import numpy as np

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from evaluators import (
    FactScoreV2Evaluator,
    FinMMEJudgeEvaluator,
    TraditionalMetricsEvaluator
)


def convert_to_json_serializable(obj):
    """转换 numpy 类型为 Python 原生类型"""
    if isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_json_serializable(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    else:
        return obj


# 路径映射
PATH_MAPPING = {
    "/data/finmme-bench/data": "$DATA_ROOT/benchmark/data",
    "/app/data": "$DATA_ROOT/benchmark/data"
}


def map_image_path(image_path: str) -> str:
    """将服务器路径映射到本地路径"""
    if not image_path:
        return ""
    for server_path, local_path in PATH_MAPPING.items():
        if image_path.startswith(server_path):
            return image_path.replace(server_path, local_path)
    return image_path


def load_results(result_file: str) -> List[Dict]:
    """加载推理结果"""
    results = []
    with open(result_file, 'r', encoding='utf-8') as f:
        for line in f:
            results.append(json.loads(line))
    return results


def load_progress(progress_file: str) -> Dict[str, Dict]:
    """加载已完成的进度"""
    completed = {}
    if Path(progress_file).exists():
        with open(progress_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    sample_id = item.get("sample_id", "")
                    if sample_id:
                        completed[sample_id] = item
                except:
                    pass
    return completed


def save_progress(progress_file: str, metrics: Dict):
    """追加保存单个样本的进度"""
    with open(progress_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(convert_to_json_serializable(metrics), ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="FinMME 完整评估")
    parser.add_argument(
        "--results", "-r",
        type=str,
        default="outputs/qwen3vl_lora_v3_results.jsonl",
        help="推理结果文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="评估结果输出路径"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制评估样本数"
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="跳过 LLM 评估（FactScore 和 Judge）"
    )

    args = parser.parse_args()

    # 自动生成输出路径
    if args.output is None:
        base_name = Path(args.results).stem
        args.output = f"outputs/{base_name}_full_eval.json"

    progress_file = args.output.replace(".json", ".progress.jsonl")

    print("=" * 70)
    print("📊 FinMME 完整评估")
    print("=" * 70)
    print(f"📁 结果文件: {args.results}")
    print(f"📁 输出文件: {args.output}")
    print()

    # 加载数据
    samples = load_results(args.results)
    if args.limit:
        samples = samples[:args.limit]
    print(f"✓ 加载了 {len(samples)} 个样本\n")

    predictions = [s.get("generated_text", "") for s in samples]
    references = [s.get("ground_truth", "") for s in samples]

    # ==================== 传统指标 ====================
    print("📈 计算传统指标 (BLEU, ROUGE, METEOR, CIDEr)...")
    traditional_eval = TraditionalMetricsEvaluator()

    traditional_results = traditional_eval.evaluate(
        predictions, references,
        use_bertscore=False,  # 跳过 BERTScore
        device="cpu"
    )
    print("✓ 传统指标计算完成\n")

    # 提取需要的指标
    overall = traditional_results.get("overall", {})
    bleu = overall.get("bleu_4", 0)  # BLEU-4
    rouge1 = overall.get("rouge1", 0)
    rougeL = overall.get("rougeL", 0)
    meteor = overall.get("meteor", 0)
    cider = overall.get("cider", 0)

    # ==================== LLM 评估 ====================
    factscore_avg = 0.0
    judge_avg = 0.0
    llm_metrics = []

    if not args.skip_llm:
        print("🤖 初始化 LLM 评估器...")
        factscore_eval = FactScoreV2Evaluator(relative_tolerance=0.03)
        judge_eval = FinMMEJudgeEvaluator(model="gpt-5")
        print("✓ 评估器初始化完成\n")

        # 加载进度
        completed = load_progress(progress_file)
        print(f"📂 断点恢复: 已完成 {len(completed)} 个样本\n")

        # 评估
        print("🔄 运行 LLM 评估 (FactScore v2 + Judge)...")
        for sample in tqdm(samples, desc="评估进度"):
            sample_id = sample.get("id", "")

            if sample_id in completed:
                llm_metrics.append(completed[sample_id])
                continue

            prediction = sample.get("generated_text", "")
            reference = sample.get("ground_truth", "")
            image_path = map_image_path(sample.get("image_path", ""))

            metrics = {"sample_id": sample_id}

            # FactScore v2
            try:
                fs = factscore_eval.evaluate(prediction, reference, image_path)
                metrics["factscore"] = {
                    "precision": fs["precision"],
                    "correct_count": fs["correct_count"],
                    "total_pred_facts": fs["total_pred_facts"]
                }
            except Exception as e:
                print(f"\n⚠️  FactScore 失败 ({sample_id}): {e}")
                metrics["factscore"] = {"error": str(e), "precision": 0}

            # Judge
            try:
                judge = judge_eval.evaluate(prediction, reference, image_path)
                metrics["judge"] = {
                    "weighted_score": judge["weighted_score"],
                    "normalized_score": judge["normalized_score"]
                }
            except Exception as e:
                print(f"\n⚠️  Judge 失败 ({sample_id}): {e}")
                metrics["judge"] = {"error": str(e), "normalized_score": 0}

            llm_metrics.append(metrics)
            save_progress(progress_file, metrics)
            time.sleep(0.2)

        print("\n✓ LLM 评估完成\n")

        # 汇总 LLM 指标
        fs_scores = [m["factscore"].get("precision", 0) for m in llm_metrics if "error" not in m.get("factscore", {})]
        judge_scores = [m["judge"].get("normalized_score", 0) for m in llm_metrics if "error" not in m.get("judge", {})]

        factscore_avg = float(np.mean(fs_scores)) if fs_scores else 0.0
        judge_avg = float(np.mean(judge_scores)) if judge_scores else 0.0

    # ==================== 输出结果 ====================
    print("\n" + "=" * 70)
    print("📊 评估结果汇总")
    print("=" * 70)
    print(f"\n{'指标':<15} {'分数':>10}")
    print("-" * 30)
    print(f"{'BLEU-4':<15} {bleu:>10.4f}")
    print(f"{'ROUGE-1':<15} {rouge1:>10.4f}")
    print(f"{'ROUGE-L':<15} {rougeL:>10.4f}")
    print(f"{'METEOR':<15} {meteor:>10.4f}")
    print(f"{'CIDEr':<15} {cider:>10.4f}")
    if not args.skip_llm:
        print(f"{'FactScore v2':<15} {factscore_avg:>10.4f}")
        print(f"{'Judge':<15} {judge_avg:>10.4f}")
    print("-" * 30)

    # 保存完整结果
    final_results = {
        "model": Path(args.results).stem.replace("_results", ""),
        "total_samples": len(samples),
        "metrics": {
            "bleu_4": bleu,
            "rouge1": rouge1,
            "rougeL": rougeL,
            "meteor": meteor,
            "cider": cider,
            "factscore_v2": factscore_avg,
            "judge": judge_avg
        },
        "traditional_details": traditional_results,
        "llm_per_sample": llm_metrics if not args.skip_llm else []
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(convert_to_json_serializable(final_results), f, ensure_ascii=False, indent=2)

    print(f"\n✓ 结果已保存: {args.output}")


if __name__ == "__main__":
    main()
