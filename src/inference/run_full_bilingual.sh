#!/bin/bash
# 全量推理 - 5个模型，1000个样本，双语提示词
# sync_300_cn: 中文提示词
# 其他: 英文提示词

cd /data/finmme-bench

echo "=========================================="
echo "全量推理 - 5个模型 x 1000样本 = 5000次推理"
echo "sync_300_cn (300): 中文提示词"
echo "其他 (700): 英文提示词"
echo "=========================================="

source /root/anaconda3/etc/profile.d/conda.sh
conda activate vl7b

MODELS=("qwen3vl-2b" "qwen3vl-4b" "qwen3vl-8b" "exp-002" "exp-005")

for model in "${MODELS[@]}"; do
    echo ""
    echo "=========================================="
    echo "推理模型: $model"
    echo "开始时间: $(date)"
    echo "=========================================="

    python3 full_inference_bilingual.py --model $model --num-gpus 8

    echo "完成时间: $(date)"
    echo ""
done

echo "=========================================="
echo "所有模型推理完成！"
echo "=========================================="

echo ""
echo "结果文件:"
ls -lh /data/finmme-bench/outputs/*_results.jsonl
