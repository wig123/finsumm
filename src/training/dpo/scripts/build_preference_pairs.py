#!/usr/bin/env python3
"""
构建 DPO 偏好对数据

从候选数据中构建偏好对:
- chosen: greedy 输出 (candidates[0])
- rejected: 随机一个 sample 输出 (candidates[1-5])

输出格式: LLaMA-Factory ShareGPT 偏好格式
"""

import json
import random
import argparse
from pathlib import Path
from typing import List, Dict


def build_preference_pairs(
    candidates_file: Path,
    output_file: Path,
    num_samples: int = 100,
    seed: int = 42
) -> List[Dict]:
    """构建偏好对数据"""

    # 加载候选数据
    with open(candidates_file, 'r', encoding='utf-8') as f:
        candidates_data = json.load(f)

    print(f"加载 {len(candidates_data)} 条候选数据")

    # 过滤掉有错误或候选数不足的样本
    valid_data = []
    for item in candidates_data:
        if 'error' in item:
            continue
        if len(item.get('candidates', [])) < 2:
            continue
        # 确保有 greedy 和至少一个 sample
        meta = item.get('candidates_meta', [])
        has_greedy = any(m.get('type') == 'greedy' for m in meta)
        has_sample = any(m.get('type') == 'sample' for m in meta)
        if has_greedy and has_sample:
            valid_data.append(item)

    print(f"有效样本: {len(valid_data)} 条")

    # 随机抽样
    random.seed(seed)
    if num_samples > len(valid_data):
        print(f"警告: 请求 {num_samples} 条，但只有 {len(valid_data)} 条有效数据")
        num_samples = len(valid_data)

    sampled = random.sample(valid_data, num_samples)
    print(f"抽样 {len(sampled)} 条")

    # 构建偏好对
    preference_pairs = []
    for item in sampled:
        candidates = item['candidates']
        meta = item['candidates_meta']

        # 找到 greedy 输出 (作为 chosen)
        greedy_idx = None
        sample_indices = []
        for i, m in enumerate(meta):
            if m.get('type') == 'greedy':
                greedy_idx = i
            elif m.get('type') == 'sample':
                sample_indices.append(i)

        if greedy_idx is None or not sample_indices:
            continue

        chosen_response = candidates[greedy_idx]

        # 随机选择一个 sample 作为 rejected
        rejected_idx = random.choice(sample_indices)
        rejected_response = candidates[rejected_idx]

        # 构建 conversations (不含最后的 gpt 回复)
        messages = item['messages']
        conversations = []
        for msg in messages:
            if msg['from'] == 'system':
                conversations.append({
                    "from": "system",
                    "value": msg['value']
                })
            elif msg['from'] == 'human':
                conversations.append({
                    "from": "human",
                    "value": msg['value']
                })
            # 不包含原始的 gpt 回复

        # LLaMA-Factory ShareGPT 偏好格式
        pair = {
            "conversations": conversations,
            "chosen": {
                "from": "gpt",
                "value": chosen_response
            },
            "rejected": {
                "from": "gpt",
                "value": rejected_response
            },
            "images": [item['image']]
        }

        preference_pairs.append(pair)

    print(f"构建 {len(preference_pairs)} 个偏好对")

    # 保存
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(preference_pairs, f, ensure_ascii=False, indent=2)

    print(f"保存到: {output_file}")

    # 统计
    print("\n=== 数据统计 ===")
    chosen_lens = [len(p['chosen']['value']) for p in preference_pairs]
    rejected_lens = [len(p['rejected']['value']) for p in preference_pairs]
    print(f"Chosen 平均长度: {sum(chosen_lens)/len(chosen_lens):.0f} 字符")
    print(f"Rejected 平均长度: {sum(rejected_lens)/len(rejected_lens):.0f} 字符")

    return preference_pairs


def main():
    parser = argparse.ArgumentParser(description="构建 DPO 偏好对数据")
    parser.add_argument(
        '--input', type=Path,
        default=Path('$DATA_ROOT/dpo/data/candidates/candidates_2000.json'),
        help='候选数据文件'
    )
    parser.add_argument(
        '--output', type=Path,
        default=Path('$DATA_ROOT/dpo/data/dpo_train_100.json'),
        help='输出偏好对文件'
    )
    parser.add_argument('--num-samples', type=int, default=100, help='抽样数量')
    parser.add_argument('--seed', type=int, default=42, help='随机种子')

    args = parser.parse_args()

    build_preference_pairs(
        candidates_file=args.input,
        output_file=args.output,
        num_samples=args.num_samples,
        seed=args.seed
    )


if __name__ == '__main__':
    main()
