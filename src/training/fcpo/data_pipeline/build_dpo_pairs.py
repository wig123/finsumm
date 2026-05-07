#!/usr/bin/env python3
"""
从评分结果构建 DPO 偏好对。

输入:
  --scores: scored_candidates.json (score_candidates.py 的输出)
  --candidates: 原始候选数据 JSON (用于获取文本)
  --source-facts: source_facts.json (可选，用于计算 r_fact metadata)

输出:
  dpo_pairs.json: LlamaFactory DPO 格式
    - 无 system prompt
    - 统一 user prompt: "<image>\n请详细分析这张金融图表。"
    - chosen = fact_score 最高的候选
    - rejected = fact_score 最低的候选
    - 附 _meta: delta_r_fact, chosen_score, rejected_score

用法:
  python build_dpo_pairs.py \
    --scores data/scored_candidates.json \
    --candidates data/candidates.json \
    --min-delta 5 \
    --output data/dpo_v4.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path

# 统一 user prompt（与 V1 DPO 训练数据一致，与 SFT 训练格式一致）
USER_PROMPT = "<image>\n请详细分析这张金融图表。"


def build_pairs(scores_data: list, candidates_data: list,
                min_delta: int = 5) -> tuple:
    """
    从评分结果构建偏好对。

    Args:
        scores_data: score_candidates.py 的输出
        candidates_data: 原始候选 JSON
        min_delta: 最小分差阈值 (1-100 scale)，低于此值的 item 跳过

    Returns:
        (pairs, stats)
    """
    # 建立候选文本索引
    cand_map = {item["index"]: item for item in candidates_data}

    pairs = []
    stats = Counter()

    for scored in scores_data:
        item_idx = scored["item_index"]
        stats["total"] += 1

        # 找到原始候选数据
        if item_idx not in cand_map:
            stats["missing_candidates"] += 1
            continue
        orig = cand_map[item_idx]

        # 获取有效分数的候选
        valid = [c for c in scored["candidates"] if c["score"] > 0]
        if len(valid) < 2:
            stats["insufficient_scores"] += 1
            continue

        # 选 best 和 worst
        best = max(valid, key=lambda c: c["score"])
        worst = min(valid, key=lambda c: c["score"])

        # best 和 worst 不能是同一个
        if best["cand_index"] == worst["cand_index"]:
            stats["same_best_worst"] += 1
            continue

        delta = best["score"] - worst["score"]
        if delta < min_delta:
            stats["below_threshold"] += 1
            continue

        # 获取文本
        chosen_text = orig["candidates"][best["cand_index"]]
        rejected_text = orig["candidates"][worst["cand_index"]]

        if not chosen_text or not rejected_text:
            stats["empty_text"] += 1
            continue

        # 构建 LlamaFactory DPO 格式
        pair = {
            "conversations": [
                {"from": "human", "value": USER_PROMPT}
            ],
            "chosen": {"from": "gpt", "value": chosen_text},
            "rejected": {"from": "gpt", "value": rejected_text},
            "images": [orig["image"]],
        }

        # 元数据（训练时不用，分析用）
        pair["_meta"] = {
            "item_index": item_idx,
            "source": orig.get("_source", ""),
            "chosen_cand_index": best["cand_index"],
            "rejected_cand_index": worst["cand_index"],
            "chosen_score": best["score"],
            "rejected_score": worst["score"],
            "delta": delta,
            "chosen_errors": best.get("errors", []),
            "rejected_errors": worst.get("errors", []),
            "has_source_facts": scored.get("has_source_facts", False),
        }

        pairs.append(pair)
        stats["success"] += 1

    return pairs, stats


def main():
    parser = argparse.ArgumentParser(description="从评分结果构建 DPO 偏好对")
    parser.add_argument("--scores", type=str, required=True, help="scored_candidates.json")
    parser.add_argument("--candidates", type=str, required=True, help="原始候选 JSON")
    parser.add_argument("--output", type=str, default=None, help="输出 DPO JSON")
    parser.add_argument("--min-delta", type=int, default=5,
                        help="最小分差阈值 (1-100 scale)，默认 5 分")
    parser.add_argument("--keep-meta", action="store_true", help="保留 _meta 字段")
    args = parser.parse_args()

    # 加载数据
    print(f"加载评分: {args.scores}")
    with open(args.scores) as f:
        scores_data = json.load(f)
    print(f"  items: {len(scores_data)}")

    print(f"加载候选: {args.candidates}")
    with open(args.candidates) as f:
        candidates_data = json.load(f)
    print(f"  items: {len(candidates_data)}")

    # 构建偏好对
    pairs, stats = build_pairs(scores_data, candidates_data, args.min_delta)

    # 输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(args.scores).parent / "dpo_v4.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存（可选去掉 _meta）
    output_data = pairs
    if not args.keep_meta:
        output_data = [{k: v for k, v in p.items() if k != "_meta"} for p in pairs]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # 同时保存带 _meta 的分析版本
    meta_path = output_path.with_name(output_path.stem + "_with_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)

    # 统计
    print("\n" + "=" * 60)
    print(f"偏好对构建完成")
    print(f"=" * 60)
    for key in ["total", "success", "below_threshold", "insufficient_scores",
                 "same_best_worst", "missing_candidates", "empty_text"]:
        if stats[key]:
            print(f"  {key}: {stats[key]}")

    if pairs:
        deltas = [p["_meta"]["delta"] for p in pairs]
        chosen_scores = [p["_meta"]["chosen_score"] for p in pairs]
        rejected_scores = [p["_meta"]["rejected_score"] for p in pairs]
        sources = Counter(p["_meta"]["source"] for p in pairs)
        has_sf = sum(1 for p in pairs if p["_meta"]["has_source_facts"])

        print(f"\n  偏好对数量: {len(pairs)}")
        print(f"  有源数据: {has_sf}, 无源数据: {len(pairs) - has_sf}")
        print(f"\n  delta (chosen-rejected):")
        print(f"    mean={sum(deltas)/len(deltas):.1f}, min={min(deltas)}, max={max(deltas)}")
        print(f"  chosen_score: mean={sum(chosen_scores)/len(chosen_scores):.1f}")
        print(f"  rejected_score: mean={sum(rejected_scores)/len(rejected_scores):.1f}")
        print(f"\n  数据源: {dict(sources)}")

        # delta 分布
        brackets = [(5, 10), (10, 20), (20, 30), (30, 50), (50, 100)]
        print(f"\n  delta 分布:")
        for lo, hi in brackets:
            cnt = sum(1 for d in deltas if lo <= d < hi)
            print(f"    [{lo:3d}, {hi:3d}): {cnt:5d} ({cnt/len(deltas):.1%})")

    print(f"\n  输出: {output_path}")
    print(f"  分析版: {meta_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
