#!/bin/bash
# 只运行 exp-002 和 exp-005 的推理 (LoRA模型)

cd /data/finmme-bench

echo "=========================================="
echo "LoRA模型推理 - exp-002 和 exp-005"
echo "=========================================="

source /root/anaconda3/etc/profile.d/conda.sh
conda activate vl7b

MODELS=("exp-002" "exp-005")

for model in "${MODELS[@]}"; do
    echo ""
    echo "=========================================="
    echo "推理模型: $model (LoRA)"
    echo "开始时间: $(date)"
    echo "=========================================="

    python3 full_inference_bilingual.py --model $model --num-gpus 8

    echo "完成时间: $(date)"
    echo ""
done

echo "=========================================="
echo "LoRA模型推理完成！"
echo "=========================================="

echo ""
echo "结果文件:"
ls -lh /data/finmme-bench/outputs/exp-*_results.jsonl
