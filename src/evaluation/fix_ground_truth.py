#!/usr/bin/env python3
"""
补充 ground_truth 到推理结果文件中
根据 source 和 id 从本地 data 目录读取正确的 analysis 文件
"""
import json
from pathlib import Path

DATA_BASE = Path("$DATA_ROOT/benchmark/data")
RESULTS_DIR = Path("$DATA_ROOT/benchmark/outputs/full_1000")

# 结果文件列表
RESULT_FILES = [
    "base_results.jsonl",
    "exp-012-ckpt640_results.jsonl",
    "exp-012-ckpt800_results.jsonl",
    "exp-010-ckpt640_results.jsonl",
    "qwen3_vl_30b_a3b_instruct_results.jsonl",
]


def get_ground_truth(sample_id: str, source: str) -> str:
    """根据 sample_id 和 source 获取 ground_truth"""
    sample_dir = DATA_BASE / source / sample_id

    if not sample_dir.exists():
        print(f"  警告: 目录不存在 {sample_dir}")
        return ""

    # 根据 source 选择文件
    if source == "sync_300_cn":
        # 中文数据集用 analysis.txt
        gt_file = sample_dir / "analysis.txt"
    else:
        # 英文数据集优先用 analysis_en.txt，没有则用 analysis.txt
        gt_file = sample_dir / "analysis_en.txt"
        if not gt_file.exists():
            gt_file = sample_dir / "analysis.txt"

    if gt_file.exists():
        with open(gt_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    else:
        print(f"  警告: ground_truth 文件不存在 {gt_file}")
        return ""


def fix_result_file(filename: str):
    """修复单个结果文件"""
    input_file = RESULTS_DIR / filename
    output_file = RESULTS_DIR / filename.replace("_results.jsonl", "_results_fixed.jsonl")

    print(f"\n处理: {filename}")

    results = []
    fixed_count = 0
    empty_count = 0

    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            sample_id = r.get("id", "")
            source = r.get("source", "")

            # 获取 ground_truth
            gt = get_ground_truth(sample_id, source)
            r["ground_truth"] = gt

            if gt:
                fixed_count += 1
            else:
                empty_count += 1

            results.append(r)

    # 写入修复后的文件
    with open(output_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"  总样本: {len(results)}")
    print(f"  有 ground_truth: {fixed_count}")
    print(f"  无 ground_truth: {empty_count}")
    print(f"  输出: {output_file}")

    return fixed_count, empty_count


def main():
    print("=" * 60)
    print("补充 ground_truth 到推理结果文件")
    print("=" * 60)

    total_fixed = 0
    total_empty = 0

    for filename in RESULT_FILES:
        fixed, empty = fix_result_file(filename)
        total_fixed += fixed
        total_empty += empty

    print("\n" + "=" * 60)
    print("完成!")
    print(f"总计有 ground_truth: {total_fixed}")
    print(f"总计无 ground_truth: {total_empty}")
    print("=" * 60)

    # 用修复后的文件替换原文件
    print("\n是否用修复后的文件替换原文件? (y/n)")
    choice = input().strip().lower()
    if choice == 'y':
        for filename in RESULT_FILES:
            original = RESULTS_DIR / filename
            fixed = RESULTS_DIR / filename.replace("_results.jsonl", "_results_fixed.jsonl")
            backup = RESULTS_DIR / filename.replace("_results.jsonl", "_results_backup.jsonl")

            # 备份原文件
            original.rename(backup)
            # 重命名修复后的文件
            fixed.rename(original)
            print(f"  已替换: {filename}")
        print("所有文件已替换完成!")


if __name__ == "__main__":
    main()
