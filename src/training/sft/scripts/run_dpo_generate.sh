#!/bin/bash
# DPO Candidate 生成脚本
# 在 GPU 服务器 Docker 容器内运行

set -e

# 配置
INPUT_FILE="/app$DATA_ROOT/dpo/sampled.json"
OUTPUT_FILE="/app$DATA_ROOT/dpo/candidates.json"
MODEL_PATH="/app/outputs/exp-005"
BASE_MODEL="/app/models/qwen3-vl-8b-instruct"

# 生成参数
NUM_CANDIDATES=4
TEMPERATURE=0.9
TOP_P=0.95

echo "=========================================="
echo "DPO Candidate 生成"
echo "=========================================="
echo "输入文件: $INPUT_FILE"
echo "输出文件: $OUTPUT_FILE"
echo "SFT 模型: $MODEL_PATH"
echo "候选数量: $NUM_CANDIDATES"
echo "温度: $TEMPERATURE"
echo "=========================================="

# 检查输入文件
if [ ! -f "$INPUT_FILE" ]; then
    echo "错误: 输入文件不存在: $INPUT_FILE"
    echo "请先执行: python scripts/build_dpo_data.py sample"
    exit 1
fi

# 检查模型
if [ ! -d "$MODEL_PATH" ]; then
    echo "错误: 模型目录不存在: $MODEL_PATH"
    exit 1
fi

# 执行生成
python /app/scripts/build_dpo_data.py generate \
    --input "$INPUT_FILE" \
    --output "$OUTPUT_FILE" \
    --model "$MODEL_PATH" \
    --base-model "$BASE_MODEL" \
    --num-candidates $NUM_CANDIDATES \
    --temperature $TEMPERATURE \
    --top-p $TOP_P

echo "=========================================="
echo "生成完成!"
echo "输出文件: $OUTPUT_FILE"
echo "=========================================="
