#!/bin/bash
# 批量运行所有模型的增量推理 (排除 qwen25vl-7b)

cd /data/finmme-bench

echo "=========================================="
echo "开始增量推理 - 5个模型，共2500个新样本 (500/模型)"
echo "=========================================="

# 激活环境
source /root/anaconda3/etc/profile.d/conda.sh
conda activate vl7b

MODELS=("qwen3vl-2b" "qwen3vl-4b" "qwen3vl-8b" "exp-002" "exp-005")

for model in "${MODELS[@]}"; do
    echo ""
    echo "=========================================="
    echo "推理模型: $model"
    echo "开始时间: $(date)"
    echo "=========================================="

    python3 run_incremental_inference.py --model $model --num-gpus 8

    echo "完成时间: $(date)"
    echo ""
done

echo "=========================================="
echo "所有模型增量推理完成！"
echo "=========================================="

# 统计结果
echo ""
echo "结果文件:"
ls -lh /data/finmme-bench/outputs/*_results.json
