#!/bin/bash
# FinMME Benchmark: Base vs SFT 对比测试
# 在 pku-247 上执行

PYTHON="/data/ww/miniconda3/envs/dpo311/bin/python3"
SCRIPT="/home1/ww/finmme-official/finmme_inference_8gpu.py"
DATASET="/home1/ww/finmme-official/finmme_1000_samples.json"
OUTPUT_DIR="/home1/ww/finmme-official/results"
BASE_MODEL="/share4/yzy/models/qwen3-vl-8b-instruct"
SFT_LORA="/share2/ww/qwen3vl-dpo/sft-checkpoint/exp-012-ckpt640"
NUM_GPUS=8

mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo "  FinMME Benchmark: Base vs SFT"
echo "============================================"

# 1. Base model
echo ""
echo "[1/2] Running Qwen3-VL-8B Base..."
$PYTHON $SCRIPT \
    --model-path "$BASE_MODEL" \
    --model-name "qwen3vl_base" \
    --dataset "$DATASET" \
    --output-dir "$OUTPUT_DIR" \
    --num-gpus $NUM_GPUS

# 2. SFT model (LoRA)
echo ""
echo "[2/2] Running Qwen3-VL-8B SFT (exp-012/ckpt-640)..."
$PYTHON $SCRIPT \
    --model-path "$BASE_MODEL" \
    --lora-path "$SFT_LORA" \
    --model-name "qwen3vl_sft_exp012" \
    --dataset "$DATASET" \
    --output-dir "$OUTPUT_DIR" \
    --num-gpus $NUM_GPUS

echo ""
echo "============================================"
echo "  Done! Results in: $OUTPUT_DIR"
echo "============================================"
echo ""
echo "Summary files:"
echo "  $OUTPUT_DIR/qwen3vl_base_summary.json"
echo "  $OUTPUT_DIR/qwen3vl_sft_exp012_summary.json"
