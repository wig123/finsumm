#!/usr/bin/env python3
"""演示单个样本的详细评估输出"""

import json
from pathlib import Path
from evaluators import FactScoreV2Evaluator, FinMMEJudgeEvaluator

# 路径映射
PATH_MAPPING = {
    "/data/finmme-bench/data": "$DATA_ROOT/benchmark/data",
    "/app/data": "$DATA_ROOT/benchmark/data"
}

def map_image_path(image_path: str) -> str:
    if not image_path:
        return ""
    for server_path, local_path in PATH_MAPPING.items():
        if image_path.startswith(server_path):
            return image_path.replace(server_path, local_path)
    return image_path

def main():
    # 加载样本
    results_file = Path("outputs/qwen3vl_lora_v3_results.jsonl")
    with open(results_file, 'r') as f:
        samples = [json.loads(line) for line in f]

    # 取第一个样本进行评估
    sample = samples[0]
    sample_id = sample.get("id", "")
    prediction = sample.get("generated_text", "")
    reference = sample.get("ground_truth", "")
    image_path = map_image_path(sample.get("image_path", ""))

    print(f"📊 样本ID: {sample_id}")
    print(f"📁 图片路径: {image_path}")
    print()

    # FactScore v2 评估
    print("=" * 60)
    print("🔍 FactScore v2 详细评估")
    print("=" * 60)

    fs_eval = FactScoreV2Evaluator(relative_tolerance=0.03)
    fs_result = fs_eval.evaluate(prediction, reference, image_path)

    print(f"\n精确度: {fs_result['precision']*100:.1f}%")
    print(f"预测事实数: {fs_result['total_pred_facts']}")
    print(f"参考事实数: {fs_result['total_ref_facts']}")
    print(f"正确匹配: {fs_result['correct_count']}")
    print(f"  - 参考匹配: {fs_result['ref_match_count']}")
    print(f"  - 图表支持: {fs_result['chart_support_count']}")
    print(f"幻觉数: {fs_result['hallucination_count']}")

    print("\n📋 参考事实:")
    for rf in fs_result.get('ref_facts', []):
        print(f"  [{rf['id']}] {rf['entity']}: {rf['value']}")

    print("\n📋 预测事实详情:")
    for detail in fs_result.get('details', []):
        status = "✓" if detail['is_correct'] else "✗"
        match_type = detail.get('match_type', 'hallucination')
        print(f"  {status} {detail['entity']}: 预测={detail['pred_value']}, 参考={detail.get('ref_value', '-')}, 图表={detail.get('chart_value', '-')} [{match_type}]")

    # Judge 评估
    print("\n" + "=" * 60)
    print("⚖️ Judge 详细评估")
    print("=" * 60)

    judge_eval = FinMMEJudgeEvaluator(model="gpt-5")
    judge_result = judge_eval.evaluate(prediction, reference, image_path)

    print(f"\n加权分数: {judge_result['weighted_score']:.2f}/5")
    print(f"归一化分数: {judge_result['normalized_score']*100:.1f}%")

    print("\n📊 各维度评分:")
    dimensions = ["faithfulness", "completeness", "analysis", "logicality", "conciseness"]
    dim_names = ["忠实度", "完整度", "分析", "逻辑性", "简洁性"]

    for dim, name in zip(dimensions, dim_names):
        score_data = judge_result['scores'].get(dim, {})
        score = score_data.get('score', 0)
        evidence = score_data.get('evidence', '')
        weight = score_data.get('weight', 0)
        print(f"\n  {name} ({weight*100:.0f}%): {score}/5")
        print(f"    证据: {evidence[:200]}{'...' if len(evidence) > 200 else ''}")

    print(f"\n💬 总体评价:")
    print(f"  {judge_result.get('overall_comment', '无')}")

    # 保存详细结果
    detailed_result = {
        "sample_id": sample_id,
        "factscore": {
            "precision": fs_result["precision"],
            "correct_count": fs_result["correct_count"],
            "total_pred_facts": fs_result["total_pred_facts"],
            "total_ref_facts": fs_result["total_ref_facts"],
            "ref_match_count": fs_result["ref_match_count"],
            "chart_support_count": fs_result["chart_support_count"],
            "hallucination_count": fs_result["hallucination_count"],
            "ref_facts": fs_result.get("ref_facts", []),
            "pred_facts": fs_result.get("pred_facts", []),
            "details": fs_result.get("details", [])
        },
        "judge": {
            "weighted_score": judge_result["weighted_score"],
            "normalized_score": judge_result["normalized_score"],
            "faithfulness": judge_result["scores"]["faithfulness"]["score"],
            "completeness": judge_result["scores"]["completeness"]["score"],
            "analysis": judge_result["scores"]["analysis"]["score"],
            "logicality": judge_result["scores"]["logicality"]["score"],
            "conciseness": judge_result["scores"]["conciseness"]["score"],
            "scores_detail": judge_result["scores"],
            "overall_comment": judge_result.get("overall_comment", "")
        }
    }

    print("\n" + "=" * 60)
    print("💾 详细结果 JSON (用于前端展示)")
    print("=" * 60)
    print(json.dumps(detailed_result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
