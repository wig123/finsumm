#!/usr/bin/env python3
"""
从 V4 fact 评分构建 FCPO 训练数据。

V3 FCPO patch 使用乘法 margin: L_i = -log σ(β × margin_i × Δlogits_i)
  margin=1.0: 标准 DPO
  margin>1.0: 加强偏好（fact 差异大的样本）
  margin<1.0: 减弱偏好（fact 差异小的样本）
  margin=0.0: 不参与训练

margin 计算: margin_i = delta_i / mean_delta（归一化到均值=1）

用法:
  python build_fcpo_data.py \
    --input data/dpo_v1_2000_with_meta.json \
    --output data/fcpo_v1.json
"""

import argparse
import json
from pathlib import Path


def build_fcpo(data: list, min_delta: int = 10) -> tuple:
    """给每条偏好对添加 margin 字段。"""
    # 过滤有 _meta 的
    valid = [d for d in data if "_meta" in d and d["_meta"].get("delta", 0) >= min_delta]

    # 计算 mean delta
    deltas = [d["_meta"]["delta"] for d in valid]
    mean_delta = sum(deltas) / len(deltas)

    result = []
    for d in valid:
        delta = d["_meta"]["delta"]
        margin = round(delta / mean_delta, 4)  # 归一化: mean margin = 1.0

        new_d = {k: v for k, v in d.items() if k != "_meta"}
        new_d["margin"] = margin
        result.append(new_d)

    stats = {
        "total": len(data),
        "valid": len(valid),
        "mean_delta": round(mean_delta, 2),
        "margin_min": round(min(d["margin"] for d in result), 4),
        "margin_max": round(max(d["margin"] for d in result), 4),
        "margin_mean": round(sum(d["margin"] for d in result) / len(result), 4),
    }
    return result, stats


def main():
    parser = argparse.ArgumentParser(description="构建 FCPO 训练数据")
    parser.add_argument("--input", type=str, required=True, help="带 _meta 的 DPO 数据")
    parser.add_argument("--output", type=str, default=None, help="输出 FCPO JSON")
    parser.add_argument("--min-delta", type=int, default=10, help="最小 delta 阈值")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)
    print(f"输入: {len(data)} 条")

    result, stats = build_fcpo(data, args.min_delta)

    output_path = args.output or args.input.replace(".json", "_fcpo.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n输出: {output_path}")
    print(f"有效: {stats['valid']} 条")
    print(f"mean_delta: {stats['mean_delta']}")
    print(f"margin: min={stats['margin_min']}, max={stats['margin_max']}, mean={stats['margin_mean']}")

    # margin 分布
    margins = [d["margin"] for d in result]
    brackets = [(0, 0.5), (0.5, 0.8), (0.8, 1.2), (1.2, 2.0), (2.0, 5.0)]
    print("\nmargin 分布:")
    for lo, hi in brackets:
        cnt = sum(1 for m in margins if lo <= m < hi)
        print(f"  [{lo:.1f}, {hi:.1f}): {cnt} ({cnt/len(margins)*100:.0f}%)")


if __name__ == "__main__":
    main()
