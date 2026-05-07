#!/usr/bin/env python3
"""
将偏好对转换为 LLaMA-Factory DPO 格式

LLaMA-Factory DPO 格式 (ShareGPT style):
{
  "conversations": [
    {"from": "human", "value": "<image>\n请详细分析这张金融图表。"}
  ],
  "chosen": {"from": "gpt", "value": "..."},
  "rejected": {"from": "gpt", "value": "..."},
  "images": ["images/xxx.png"]
}
"""

import json
import argparse
from pathlib import Path
from collections import Counter


def convert_to_dpo_format(
    sampled_data: list,
    preference_data: list,
    output_path: str
):
    """转换为 LLaMA-Factory DPO 格式"""

    # 建立索引映射
    sampled_map = {item["index"]: item for item in sampled_data}
    preference_map = {item["index"]: item for item in preference_data}

    dpo_data = []
    stats = {
        "total": 0,
        "success": 0,
        "skipped_error": 0,
        "skipped_missing": 0,
    }

    for idx in sorted(sampled_map.keys()):
        stats["total"] += 1

        if idx not in preference_map:
            stats["skipped_missing"] += 1
            continue

        pref = preference_map[idx]
        if pref.get("status") != "success":
            stats["skipped_error"] += 1
            continue

        sample = sampled_map[idx]
        chosen_idx = pref["chosen_idx"]
        rejected_idx = pref["rejected_idx"]

        # 获取 chosen 和 rejected 文本
        chosen_text = sample["candidates"][chosen_idx]
        rejected_text = sample["candidates"][rejected_idx]

        # 构建 DPO 格式
        dpo_item = {
            "conversations": [
                {
                    "from": "human",
                    "value": "<image>\n请详细分析这张金融图表。"
                }
            ],
            "chosen": {
                "from": "gpt",
                "value": chosen_text
            },
            "rejected": {
                "from": "gpt",
                "value": rejected_text
            },
            "images": [sample["image"]]
        }

        # 添加元数据（可选，用于调试）
        dpo_item["_meta"] = {
            "original_index": idx,
            "source": sample.get("_source", ""),
            "chosen_idx": chosen_idx,
            "rejected_idx": rejected_idx,
            "rejection_type": pref.get("rejection_type", ""),
            "factual_errors": pref.get("factual_errors", []),
            "reasoning": pref.get("reasoning", "")
        }

        dpo_data.append(dpo_item)
        stats["success"] += 1

    # 保存
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dpo_data, f, ensure_ascii=False, indent=2)

    # 同时生成不带 _meta 的干净版本
    clean_data = []
    for item in dpo_data:
        clean_item = {k: v for k, v in item.items() if k != "_meta"}
        clean_data.append(clean_item)

    clean_path = str(output_path).replace(".json", "_clean.json")
    with open(clean_path, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, ensure_ascii=False, indent=2)

    return stats, dpo_data


def main():
    parser = argparse.ArgumentParser(description="转换为 LLaMA-Factory DPO 格式")
    parser.add_argument("--sampled", type=str, default="data/sampled/sampled_1000.json")
    parser.add_argument("--preference", type=str, default="data/preference/preference_pairs.json")
    parser.add_argument("--output", type=str, default="data/dpo/dpo_train.json")

    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    # 加载数据
    with open(base_dir / args.sampled, "r", encoding="utf-8") as f:
        sampled_data = json.load(f)

    with open(base_dir / args.preference, "r", encoding="utf-8") as f:
        preference_data = json.load(f)

    print("=" * 70)
    print("📊 转换为 LLaMA-Factory DPO 格式")
    print("=" * 70)
    print(f"📁 Sampled: {args.sampled} ({len(sampled_data)} 条)")
    print(f"📁 Preference: {args.preference} ({len(preference_data)} 条)")
    print(f"📁 Output: {args.output}")
    print()

    # 转换
    stats, dpo_data = convert_to_dpo_format(
        sampled_data,
        preference_data,
        base_dir / args.output
    )

    print("📊 统计:")
    print(f"  总数: {stats['total']}")
    print(f"  成功: {stats['success']}")
    print(f"  跳过 (错误): {stats['skipped_error']}")
    print(f"  跳过 (缺失): {stats['skipped_missing']}")

    # 数据源分布
    src_dist = Counter(item["_meta"]["source"] for item in dpo_data)
    print("\n📊 数据源分布:")
    for src, cnt in src_dist.items():
        print(f"  {src}: {cnt}")

    print(f"\n✓ 已保存: {base_dir / args.output}")
    print(f"✓ 干净版本: {str(base_dir / args.output).replace('.json', '_clean.json')}")


if __name__ == "__main__":
    main()
