#!/usr/bin/env python3
"""
FCPO 数据构建 v2 — 区分有/无 fact 信号的样本。

Margin 策略（乘法 margin: L = -log σ(β × margin × Δlogits)）:
  - 有源数据 (has_source_facts=True): margin = delta / mean_delta_sf（归一化，均值≈1）
    → fact 信号可靠，delta 大的加强，delta 小的减弱
  - 无源数据 (has_source_facts=False): margin = 1.0（标准 DPO）
    → 仅靠图片的评分不够可靠，退化为标准 DPO 强度

注：当前数据 pipeline 保证所有 pair 的 chosen_score > rejected_score（delta >= 10），
不存在负 delta 需要翻转的情况。翻转逻辑在 build_dpo_pairs.py 的选对阶段已经隐式处理
（chosen = max score, rejected = min score）。

用法:
  python build_fcpo_data_v2.py \
    --input data/dpo_merged_with_meta.json \
    --output data/fcpo_merged_v2.json
"""

import argparse
import json
from pathlib import Path


def build_fcpo_v2(data: list, min_delta: int = 10) -> tuple:
    """
    构建 FCPO 数据：有源数据按 delta 加权，无源数据 margin=1.0。
    """
    valid = [d for d in data if "_meta" in d and d["_meta"].get("delta", 0) >= min_delta]

    # 分组
    with_sf = [d for d in valid if d["_meta"]["has_source_facts"]]
    without_sf = [d for d in valid if not d["_meta"]["has_source_facts"]]

    # 有源数据的 mean delta（用于归一化）
    if with_sf:
        mean_delta_sf = sum(d["_meta"]["delta"] for d in with_sf) / len(with_sf)
    else:
        mean_delta_sf = 20.0  # fallback

    result = []
    for d in valid:
        new_d = {k: v for k, v in d.items() if k != "_meta"}

        if d["_meta"]["has_source_facts"]:
            # 有源数据：按 delta 归一化
            margin = round(d["_meta"]["delta"] / mean_delta_sf, 4)
        else:
            # 无源数据：标准 DPO 强度
            margin = 1.0

        new_d["margin"] = margin
        result.append(new_d)

    # 统计
    sf_margins = [d["margin"] for d in result if d.get("margin") != 1.0 or
                  any(valid_d["_meta"]["has_source_facts"] for valid_d in valid
                      if valid_d.get("images") == d.get("images"))]

    # 简单统计
    all_margins = [d["margin"] for d in result]
    sf_count = len(with_sf)
    nosf_count = len(without_sf)
    sf_margins_list = [d["_meta"]["delta"] / mean_delta_sf for d in with_sf]
    nosf_margins_list = [1.0] * nosf_count

    stats = {
        "total": len(data),
        "valid": len(valid),
        "with_source_facts": sf_count,
        "without_source_facts": nosf_count,
        "mean_delta_sf": round(mean_delta_sf, 2),
        "sf_margin_mean": round(sum(sf_margins_list) / len(sf_margins_list), 4) if sf_margins_list else 0,
        "sf_margin_min": round(min(sf_margins_list), 4) if sf_margins_list else 0,
        "sf_margin_max": round(max(sf_margins_list), 4) if sf_margins_list else 0,
        "overall_margin_mean": round(sum(all_margins) / len(all_margins), 4),
    }
    return result, stats


def main():
    parser = argparse.ArgumentParser(description="构建 FCPO v2 数据")
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--min-delta", type=int, default=10)
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)
    print(f"输入: {len(data)} 条")

    result, stats = build_fcpo_v2(data, args.min_delta)

    output_path = args.output or args.input.replace(".json", "_fcpo_v2.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n输出: {output_path}")
    print(f"有效: {stats['valid']} 条")
    print(f"  有源数据: {stats['with_source_facts']} (margin 按 delta 加权，均值={stats['sf_margin_mean']:.2f})")
    print(f"  无源数据: {stats['without_source_facts']} (margin=1.0 标准 DPO)")
    print(f"  mean_delta_sf: {stats['mean_delta_sf']}")
    print(f"  有源 margin: min={stats['sf_margin_min']}, max={stats['sf_margin_max']}")
    print(f"  整体 margin 均值: {stats['overall_margin_mean']}")

    # margin 分布
    margins = [d["margin"] for d in result]
    print(f"\nmargin 分布:")
    brackets = [(0, 0.5), (0.5, 0.8), (0.8, 1.0), (1.0, 1.01), (1.01, 1.5), (1.5, 2.5), (2.5, 5.0)]
    for lo, hi in brackets:
        cnt = sum(1 for m in margins if lo <= m < hi)
        label = f"[{lo:.1f}, {hi:.1f})" if hi != 1.01 else "=1.0 (标准DPO)"
        if lo == 1.0 and hi == 1.01:
            cnt = sum(1 for m in margins if m == 1.0)
            label = "=1.0 (标准DPO)"
        print(f"  {label:<20s}: {cnt:>5d} ({cnt/len(margins)*100:.0f}%)")


if __name__ == "__main__":
    main()
