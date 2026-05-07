#!/usr/bin/env python3
"""
从 candidates_2000.json 中抽样 1000 样本

抽样规则:
- finmme: 200 (从 254 中选)
- fin-chart: 200 (从 312 中选)
- v4_synthesis: 300 (从 534 中选)
- v3_synthesis: 300 (从 900 中选)
"""

import json
import random
from pathlib import Path
from collections import defaultdict

# 配置
SAMPLE_CONFIG = {
    "finmme": 200,
    "fin-chart": 200,
    "v4_synthesis": 300,
    "v3_synthesis": 300,
}

SEED = 42


def main():
    random.seed(SEED)

    # 加载数据
    input_path = Path(__file__).parent.parent / "data/candidates/candidates_2000.json"
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"加载 {len(data)} 条数据")

    # 按数据源分组
    by_source = defaultdict(list)
    for item in data:
        by_source[item["_source"]].append(item)

    print("\n原始分布:")
    for src, items in sorted(by_source.items()):
        print(f"  {src}: {len(items)}")

    # 抽样
    sampled = []
    for source, target_count in SAMPLE_CONFIG.items():
        pool = by_source[source]
        if len(pool) < target_count:
            print(f"警告: {source} 只有 {len(pool)} 条，需要 {target_count}")
            selected = pool
        else:
            selected = random.sample(pool, target_count)
        sampled.extend(selected)
        print(f"  {source}: 抽样 {len(selected)} 条")

    # 重新分配索引
    for i, item in enumerate(sampled):
        item["original_index"] = item["index"]
        item["index"] = i

    # 打乱顺序
    random.shuffle(sampled)
    for i, item in enumerate(sampled):
        item["index"] = i

    print(f"\n总计抽样: {len(sampled)} 条")

    # 保存
    output_path = Path(__file__).parent.parent / "data/sampled/sampled_1000.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sampled, f, ensure_ascii=False, indent=2)

    print(f"已保存到: {output_path}")

    # 验证分布
    print("\n抽样后分布:")
    sampled_dist = defaultdict(int)
    for item in sampled:
        sampled_dist[item["_source"]] += 1
    for src, cnt in sorted(sampled_dist.items()):
        print(f"  {src}: {cnt}")


if __name__ == "__main__":
    main()
