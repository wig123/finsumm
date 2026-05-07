#!/usr/bin/env python3
"""从 FinMME 全量数据中排除 SFT 训练用过的图片"""
import json
from pathlib import Path

FULL_DATASET = "/home1/ww/finmme-official/finmme_full_11099.json"
OUTPUT = "/home1/ww/finmme-official/finmme_clean_decontaminated.json"

# SFT 训练中使用的 FinMME 图片 ID（从 finmme_000002~finmme_001254，共 800 张）
SFT_CONTAMINATED_IDS = set()
with open("/home1/ww/finmme-official/sft_finmme_ids.txt") as f:
    for line in f:
        line = line.strip()
        if line:
            SFT_CONTAMINATED_IDS.add(int(line))

print(f"SFT contaminated IDs: {len(SFT_CONTAMINATED_IDS)}")
print(f"ID range: {min(SFT_CONTAMINATED_IDS)} ~ {max(SFT_CONTAMINATED_IDS)}")

with open(FULL_DATASET) as f:
    all_samples = json.load(f)

print(f"Full dataset: {len(all_samples)}")

# 过滤
clean = [s for s in all_samples if s["id"] not in SFT_CONTAMINATED_IDS]
excluded = [s for s in all_samples if s["id"] in SFT_CONTAMINATED_IDS]

print(f"Excluded (contaminated): {len(excluded)}")
print(f"Clean (decontaminated): {len(clean)}")

# 按 question_type 统计
from collections import Counter
clean_dist = Counter(s["question_type"] for s in clean)
excluded_dist = Counter(s["question_type"] for s in excluded)
print(f"\nClean distribution: {dict(clean_dist)}")
print(f"Excluded distribution: {dict(excluded_dist)}")

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False, indent=2)

print(f"\nSaved to {OUTPUT}")
