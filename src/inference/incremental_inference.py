#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量推理脚本 - 只推理新增样本
对比 dataset_index_700.json 和已有结果，找出未推理的样本
"""
import os
os.environ['NCCL_P2P_DISABLE'] = '1'
os.environ['NCCL_IB_DISABLE'] = '1'

import json
import argparse
from pathlib import Path

def get_existing_ids(results_file: Path) -> set:
    """获取已推理的样本ID"""
    ids = set()
    if results_file.exists():
        with open(results_file) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    ids.add(data["id"])
                except:
                    pass
    return ids

def filter_new_samples(dataset_file: str, results_file: str) -> list:
    """过滤出未推理的样本"""
    with open(dataset_file) as f:
        all_samples = json.load(f)

    existing_ids = get_existing_ids(Path(results_file))
    new_samples = [s for s in all_samples if s["id"] not in existing_ids]

    print(f"全部样本: {len(all_samples)}")
    print(f"已推理: {len(existing_ids)}")
    print(f"待推理: {len(new_samples)}")

    return new_samples

def main():
    parser = argparse.ArgumentParser(description="增量推理 - 只推理新增样本")
    parser.add_argument("--model", type=str, required=True, help="模型名称")
    parser.add_argument("--dataset", type=str, default="/data/finmme-bench/dataset_index_700.json")
    parser.add_argument("--results", type=str, help="已有结果文件路径")
    parser.add_argument("--output", type=str, help="增量结果输出路径")
    args = parser.parse_args()

    # 默认路径
    if not args.results:
        args.results = f"/data/finmme-bench/outputs/{args.model}_results.jsonl"
    if not args.output:
        args.output = f"/data/finmme-bench/outputs/{args.model}_incremental.json"

    # 找出新样本
    new_samples = filter_new_samples(args.dataset, args.results)

    if not new_samples:
        print("没有新样本需要推理")
        return

    # 保存新样本索引供推理脚本使用
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(new_samples, f, ensure_ascii=False, indent=2)

    print(f"\n新样本索引已保存到: {args.output}")
    print(f"来源分布:")
    source_count = {}
    for s in new_samples:
        src = s.get("source", "unknown")
        source_count[src] = source_count.get(src, 0) + 1
    for src, cnt in sorted(source_count.items()):
        print(f"  {src}: {cnt}")

if __name__ == "__main__":
    main()
