#!/usr/bin/env python3
"""
FinMME 评估脚本 v3 (Judge Only)
使用 Judge 多维评分，保存完整详细数据用于可视化
指标：BLEU | ROUGE-1 | ROUGE-L | CIDEr | METEOR | Judge
"""

import os
import sys
import json
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
import numpy as np
import threading

sys.path.insert(0, str(Path(__file__).parent))

from evaluators import (
    FinMMEJudgeEvaluator,
    TraditionalMetricsEvaluator
)


def convert_to_json_serializable(obj):
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
    return obj


# 路径映射
PATH_MAPPING = {
    "/data/finmme-bench/data": "$DATA_ROOT/benchmark/data",
    "$DATA_ROOT/benchmark/data": "$DATA_ROOT/benchmark/data",
    "/data/ww/finmme-benchmark/data": "$DATA_ROOT/benchmark/data",
    "/data/ww/finmme-bench/data": "$DATA_ROOT/benchmark/data",
    "/home/ww/finmme-benchmark/data": "$DATA_ROOT/benchmark/data",
    "/home/ww/finmme-bench/data": "$DATA_ROOT/benchmark/data",
    "/app/data": "$DATA_ROOT/benchmark/data"
}


def map_image_path(image_path: str) -> str:
    if not image_path:
        return ""
    for server_path, local_path in PATH_MAPPING.items():
        if image_path.startswith(server_path):
            return image_path.replace(server_path, local_path)
    return image_path


def load_results(result_file: str) -> List[Dict]:
    results = []
    with open(result_file, 'r', encoding='utf-8') as f:
        for line in f:
            results.append(json.loads(line))
    return results


def load_progress(progress_file: str) -> Dict[str, Dict]:
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


class ConcurrentEvaluatorV3:
    """并发评估器 - 仅使用 Judge"""

    def __init__(
        self,
        concurrency: int = 8,
        judge_model: str = "gemini-2.5-flash-lite-preview-09-2025",
        judge_api_key: str = None,
        judge_base_url: str = "<YOUR_LLM_PROXY>/v1"
    ):
        self.concurrency = concurrency
        self.judge_model = judge_model
        # 每个线程使用独立的评估器实例
        self.judge_evaluators = [
            FinMMEJudgeEvaluator(
                model=judge_model,
                api_key=judge_api_key,
                base_url=judge_base_url
            )
            for _ in range(concurrency)
        ]
        self.progress_lock = threading.Lock()

    def evaluate_sample(
        self,
        sample: Dict,
        worker_id: int,
        progress_file: str
    ) -> Dict:
        """评估单个样本，保存完整详细数据"""
        sample_id = sample.get("id", "")
        prediction = sample.get("generated_text", "")
        reference = sample.get("ground_truth", "")
        image_path = map_image_path(sample.get("image_path", ""))

        metrics = {"sample_id": sample_id}

        judge_eval = self.judge_evaluators[worker_id]

        # Judge - 保存完整详情
        try:
            judge_result = judge_eval.evaluate(prediction, reference, image_path)
            metrics["judge"] = {
                "weighted_score": judge_result["weighted_score"],
                "normalized_score": judge_result["normalized_score"],
                "faithfulness": judge_result["scores"]["faithfulness"]["score"],
                "completeness": judge_result["scores"]["completeness"]["score"],
                "analysis": judge_result["scores"]["analysis"]["score"],
                "conciseness": judge_result["scores"]["conciseness"]["score"],
                # 详细数据用于可视化
                "scores_detail": judge_result["scores"],
                "overall_comment": judge_result.get("overall_comment", "")
            }
        except Exception as e:
            metrics["judge"] = {"error": str(e), "normalized_score": 0}

        # 保存进度（线程安全）
        with self.progress_lock:
            with open(progress_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(convert_to_json_serializable(metrics), ensure_ascii=False) + "\n")

        return metrics

    def evaluate_batch(
        self,
        samples: List[Dict],
        progress_file: str,
        completed: Dict[str, Dict]
    ) -> List[Dict]:
        """并发批量评估"""
        results = list(completed.values())
        pending_samples = [s for s in samples if s.get("id", "") not in completed]

        if not pending_samples:
            print("✓ 所有样本已完成评估")
            return results

        print(f"📊 待评估样本: {len(pending_samples)}")

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {
                executor.submit(
                    self.evaluate_sample,
                    sample,
                    i % self.concurrency,
                    progress_file
                ): sample
                for i, sample in enumerate(pending_samples)
            }

            for future in tqdm(as_completed(futures), total=len(futures), desc="Judge评估"):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    sample = futures[future]
                    print(f"\n⚠️ 评估失败 ({sample.get('id', '')}): {e}")
                    results.append({
                        "sample_id": sample.get("id", ""),
                        "judge": {"error": str(e), "normalized_score": 0}
                    })

        return results


def main():
    parser = argparse.ArgumentParser(description="FinMME 评估 v3 (Judge Only)")
    parser.add_argument("--results", "-r", type=str, required=True, help="结果文件路径")
    parser.add_argument("--output", "-o", type=str, default=None, help="输出文件路径")
    parser.add_argument("--limit", type=int, default=None, help="限制评估样本数")
    parser.add_argument("--concurrency", "-c", type=int, default=8, help="并发数")
    parser.add_argument("--skip-llm", action="store_true", help="跳过 LLM 评估")
    parser.add_argument("--judge-model", type=str, default="gemini-2.5-flash-lite-preview-09-2025", help="Judge 模型名称")
    parser.add_argument("--judge-api-key", type=str, default=None, help="Judge API 密钥")
    parser.add_argument("--judge-base-url", type=str, default="<YOUR_LLM_PROXY>/v1", help="Judge API base URL")

    args = parser.parse_args()

    if args.output is None:
        base_name = Path(args.results).stem
        args.output = f"outputs/{base_name}_v3_eval.json"

    progress_file = args.output.replace(".json", ".progress.jsonl")

    print("=" * 70)
    print("📊 FinMME 评估 v3 (Judge Only)")
    print("=" * 70)
    print(f"📁 结果文件: {args.results}")
    print(f"📁 输出文件: {args.output}")
    print(f"🔄 并发数: {args.concurrency}")
    print()

    # 加载数据
    samples = load_results(args.results)
    if args.limit:
        samples = samples[:args.limit]
    print(f"✓ 加载了 {len(samples)} 个样本\n")

    predictions = [s.get("generated_text", "") for s in samples]
    references = [s.get("ground_truth", "") for s in samples]

    # 传统指标
    print("📈 计算传统指标 (BLEU, ROUGE, METEOR, CIDEr)...")
    traditional_eval = TraditionalMetricsEvaluator()
    traditional_results = traditional_eval.evaluate(predictions, references, use_bertscore=False, device="cpu")
    print("✓ 传统指标计算完成\n")

    overall = traditional_results.get("overall", {})
    bleu = overall.get("bleu_4", 0)
    rouge1 = overall.get("rouge1", 0)
    rougeL = overall.get("rougeL", 0)
    meteor = overall.get("meteor", 0)
    cider = overall.get("cider", 0)

    # LLM 评估
    judge_avg = 0.0
    llm_metrics = []

    if not args.skip_llm:
        print("🤖 初始化并发评估器 (Judge)...")
        print(f"   模型: {args.judge_model}")
        print(f"   API: {args.judge_base_url}")
        evaluator = ConcurrentEvaluatorV3(
            concurrency=args.concurrency,
            judge_model=args.judge_model,
            judge_api_key=args.judge_api_key,
            judge_base_url=args.judge_base_url
        )
        print(f"✓ 已创建 {args.concurrency} 个评估器实例\n")

        completed = load_progress(progress_file)
        print(f"📂 断点恢复: 已完成 {len(completed)} 个样本\n")

        llm_metrics = evaluator.evaluate_batch(samples, progress_file, completed)
        print("\n✓ LLM 评估完成\n")

        judge_scores = [m["judge"].get("normalized_score", 0) for m in llm_metrics if "error" not in m.get("judge", {})]
        judge_avg = float(np.mean(judge_scores)) if judge_scores else 0.0
        print(f"📊 有效样本数: Judge={len(judge_scores)}")

    # 输出结果
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
        print(f"{'Judge':<15} {judge_avg:>10.4f}")
    print("-" * 30)

    # 保存结果
    final_results = {
        "model": Path(args.results).stem.replace("_results", ""),
        "total_samples": len(samples),
        "metrics": {
            "bleu_4": bleu,
            "rouge1": rouge1,
            "rougeL": rougeL,
            "meteor": meteor,
            "cider": cider,
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
