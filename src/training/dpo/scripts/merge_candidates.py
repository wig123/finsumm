#!/usr/bin/env python3
"""
合并 8 卡候选生成结果

使用方式:
    python merge_candidates.py
    python merge_candidates.py --input-dir /app$DATA_ROOT/dpo --output /app$DATA_ROOT/dpo/candidates_2000.json
"""

import json
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="合并 8 卡候选结果")
    parser.add_argument(
        "--input-dir", type=Path,
        default=Path("$DATA_ROOT/sft/data/dpo"),
        help="输入目录"
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("$DATA_ROOT/sft$DATA_ROOT/dpo/candidates_2000.json"),
        help="输出文件"
    )
    parser.add_argument("--num-gpus", type=int, default=8, help="GPU 数量")
    args = parser.parse_args()

    print("=" * 50)
    print("合并 8 卡候选生成结果")
    print("=" * 50)

    all_results = []
    missing_gpus = []

    for gpu_id in range(args.num_gpus):
        input_file = args.input_dir / f"candidates_gpu{gpu_id}.json"

        if not input_file.exists():
            print(f"GPU {gpu_id}: 文件不存在 - {input_file}")
            missing_gpus.append(gpu_id)
            continue

        with open(input_file) as f:
            results = json.load(f)

        print(f"GPU {gpu_id}: {len(results)} 条样本")
        all_results.extend(results)

    if missing_gpus:
        print(f"\n警告: GPU {missing_gpus} 的结果缺失!")

    # 按 index 排序
    all_results.sort(key=lambda x: x['index'])

    # 检查完整性
    expected_indices = set(range(len(all_results)))
    actual_indices = set(r['index'] for r in all_results)

    if expected_indices != actual_indices:
        missing = expected_indices - actual_indices
        extra = actual_indices - expected_indices
        if missing:
            print(f"警告: 缺失索引: {sorted(missing)[:10]}... (共 {len(missing)} 个)")
        if extra:
            print(f"警告: 额外索引: {sorted(extra)[:10]}...")

    # 保存
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("")
    print("=" * 50)
    print(f"合并完成!")
    print(f"  总样本数: {len(all_results)}")
    print(f"  输出文件: {args.output}")

    # 统计候选数
    total_candidates = sum(len(r.get('candidates', [])) for r in all_results)
    avg_candidates = total_candidates / len(all_results) if all_results else 0
    print(f"  总候选数: {total_candidates}")
    print(f"  平均候选: {avg_candidates:.1f} 个/样本")

    # 统计错误
    errors = [r for r in all_results if 'error' in r]
    if errors:
        print(f"  错误样本: {len(errors)}")

    print("=" * 50)

if __name__ == "__main__":
    main()
