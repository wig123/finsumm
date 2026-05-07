#!/bin/bash
# 批量评估 7 个 checkpoint + 1 个 API 模型

cd $DATA_ROOT/benchmark

RESULTS_DIR="outputs/benchmark_7ckpt"
EVAL_DIR="outputs/benchmark_7ckpt/eval_results"
mkdir -p "$EVAL_DIR"

# 所有结果文件
RESULT_FILES=(
    "exp-002-ckpt330_results.jsonl"
    "exp-002-ckpt528_results.jsonl"
    "exp-005-ckpt396_results.jsonl"
    "exp-009-ckpt640_results.jsonl"
    "exp-010-ckpt640_results.jsonl"
    "exp-012-ckpt640_results.jsonl"
    "exp-012-ckpt800_results.jsonl"
    "qwen3_vl_30b_a3b_instruct_results.jsonl"
)

for result_file in "${RESULT_FILES[@]}"; do
    model_name="${result_file%_results.jsonl}"
    echo "=========================================="
    echo "评估: $model_name"
    echo "=========================================="

    python run_eval_v3.py \
        --results "$RESULTS_DIR/$result_file" \
        --output "$EVAL_DIR/${model_name}_eval.json" \
        --concurrency 8

    echo ""
done

echo "所有评估完成！"
