#!/bin/bash
# 批量推理脚本 - 6 个模型 × 485 张图片
# 使用方法: ./run_all_inference.sh [model_name]
# 不带参数则运行全部模型

set -e

# 切换到脚本目录
cd /data/finmme-bench

# 激活环境
source /root/anaconda3/etc/profile.d/conda.sh
conda activate vl7b

echo "=============================================="
echo "FinMME Benchmark 批量推理"
echo "数据集: 485 张图片"
echo "GPU: 8 × RTX 4090"
echo "=============================================="

# 基座模型列表
BASE_MODELS=("qwen25vl-7b" "qwen3vl-2b" "qwen3vl-4b" "qwen3vl-8b")

# LoRA 模型列表
LORA_MODELS=("exp-002" "exp-005")

run_base_model() {
    local model=$1
    echo ""
    echo ">>> 开始推理: $model"
    echo ">>> 时间: $(date)"
    python base_model_inference.py --model $model
    echo ">>> 完成: $model"
    echo ""
}

run_lora_model() {
    local model=$1
    echo ""
    echo ">>> 开始推理: $model (LoRA)"
    echo ">>> 时间: $(date)"
    python lora_inference_8gpu.py --model $model
    echo ">>> 完成: $model"
    echo ""
}

if [ $# -eq 0 ]; then
    # 运行全部模型
    echo "运行全部 6 个模型..."

    for model in "${BASE_MODELS[@]}"; do
        run_base_model $model
    done

    for model in "${LORA_MODELS[@]}"; do
        run_lora_model $model
    done

    echo "=============================================="
    echo "全部推理完成!"
    echo "结果保存在: /data/finmme-bench/outputs/"
    echo "=============================================="
    ls -la outputs/*_results.jsonl 2>/dev/null || echo "暂无结果文件"

else
    # 运行指定模型
    model=$1

    # 检查是基座还是 LoRA
    if [[ " ${BASE_MODELS[@]} " =~ " ${model} " ]]; then
        run_base_model $model
    elif [[ " ${LORA_MODELS[@]} " =~ " ${model} " ]]; then
        run_lora_model $model
    else
        echo "错误: 未知模型 '$model'"
        echo "可用的基座模型: ${BASE_MODELS[*]}"
        echo "可用的LoRA模型: ${LORA_MODELS[*]}"
        exit 1
    fi
fi
