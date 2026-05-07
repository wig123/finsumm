#!/bin/bash
# 8 GPU 并行推理脚本
# 使用独立进程避免 multiprocessing 环境问题

set -e

MODEL=${1:-qwen3}
DATASET=${2:-dataset_index.json}

echo "=============================================="
echo "8 GPU 并行推理"
echo "模型: $MODEL"
echo "数据集: $DATASET"
echo "=============================================="

# 使用完整 Python 路径
PYTHON=/root/anaconda3/envs/vl7b/bin/python

# 清理旧结果
rm -f outputs/${MODEL}_gpu*.jsonl outputs/${MODEL}_vllm_gpu*.jsonl

# 启动 8 个 GPU 进程
for gpu in 0 1 2 3 4 5 6 7; do
    echo "启动 GPU $gpu (分片 $gpu/8)..."
    CUDA_VISIBLE_DEVICES=$gpu $PYTHON vllm_inference.py \
        --model $MODEL \
        --dataset $DATASET \
        --split "$gpu/8" \
        --gpu $gpu \
        > outputs/gpu${gpu}.log 2>&1 &
done

echo ""
echo "所有 GPU 进程已启动，等待完成..."
echo "可用 'tail -f outputs/gpu*.log' 查看进度"
echo ""

# 等待所有后台进程
wait

echo "=============================================="
echo "所有 GPU 完成，合并结果..."
echo "=============================================="

# 合并结果
$PYTHON -c "
import json
from pathlib import Path
import numpy as np

output_dir = Path('outputs')
model_name = '$MODEL'
all_results = []

# 读取所有 GPU 的结果
for gpu_id in range(8):
    result_file = output_dir / f'{model_name}_vllm_gpu{gpu_id}_results.jsonl'
    if result_file.exists():
        with open(result_file) as f:
            for line in f:
                all_results.append(json.loads(line))
        print(f'GPU {gpu_id}: {sum(1 for _ in open(result_file))} 条结果')

# 按ID排序
all_results.sort(key=lambda x: x['id'])

# 保存合并结果
merged_file = output_dir / f'{model_name}_8gpu_results.jsonl'
with open(merged_file, 'w', encoding='utf-8') as f:
    for r in all_results:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

# 统计
success = [r for r in all_results if 'error' not in r]
failed = [r for r in all_results if 'error' in r]

stats = {
    'model': model_name,
    'total_samples': len(all_results),
    'success_count': len(success),
    'failed_count': len(failed),
    'success_rate': len(success) / len(all_results) if all_results else 0,
    'avg_inference_time': np.mean([r['inference_time'] for r in success]) if success else 0,
    'total_time': sum([r['inference_time'] for r in success]),
}

stats_file = output_dir / f'{model_name}_8gpu_stats.json'
with open(stats_file, 'w', encoding='utf-8') as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print()
print('='*60)
print(f'{model_name.upper()} 8GPU 推理完成')
print('='*60)
print(f\"总样本数: {stats['total_samples']}\")
print(f\"成功: {stats['success_count']} | 失败: {stats['failed_count']}\")
print(f\"成功率: {stats['success_rate']:.2%}\")
print(f\"平均推理时间: {stats['avg_inference_time']:.2f}s\")
print(f\"总推理时间: {stats['total_time']:.1f}s ({stats['total_time']/60:.1f}min)\")
print(f\"结果文件: {merged_file}\")
print('='*60)
"

echo ""
echo "完成！"
