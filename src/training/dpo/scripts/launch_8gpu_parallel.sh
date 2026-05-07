#!/bin/bash
# 8 卡并行候选生成启动脚本
#
# 使用方式:
#   ./launch_8gpu_parallel.sh          # 启动所有 8 张卡
#   ./launch_8gpu_parallel.sh 0 3      # 只启动 GPU 0-3
#   ./launch_8gpu_parallel.sh status   # 查看运行状态
#   ./launch_8gpu_parallel.sh logs 0   # 查看 GPU 0 的日志
#   ./launch_8gpu_parallel.sh stop     # 停止所有任务

set -e

# 配置
TOTAL_SAMPLES=2000
NUM_GPUS=8
SAMPLES_PER_GPU=$((TOTAL_SAMPLES / NUM_GPUS))  # 250

IMAGE="qwen3vl-sft:cu124-lf"
INPUT_FILE="/app$DATA_ROOT/dpo/sampled_2000.json"
OUTPUT_DIR="/app/data/dpo"
MODEL_PATH="/app/outputs/exp-012/checkpoint-640"
BASE_MODEL="/app/models/qwen3-vl-8b-instruct"

# 容器名前缀
CONTAINER_PREFIX="dpo-gen-gpu"

# 函数：启动单个 GPU 任务
start_gpu() {
    local gpu_id=$1
    local start_idx=$((gpu_id * SAMPLES_PER_GPU))
    local end_idx=$((start_idx + SAMPLES_PER_GPU))

    # 最后一个 GPU 处理剩余样本
    if [ $gpu_id -eq $((NUM_GPUS - 1)) ]; then
        end_idx=$TOTAL_SAMPLES
    fi

    local container_name="${CONTAINER_PREFIX}${gpu_id}"
    local output_file="${OUTPUT_DIR}/candidates_gpu${gpu_id}.json"

    echo "启动 GPU $gpu_id: 样本 [$start_idx, $end_idx)"

    # 检查是否已存在
    if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
        echo "  容器 $container_name 已存在，先删除..."
        docker rm -f "$container_name" >/dev/null 2>&1 || true
    fi

    docker run -d \
        --name "$container_name" \
        --gpus "\"device=$gpu_id\"" \
        --ipc=host \
        -e TORCHDYNAMO_DISABLE=1 \
        -e TORCH_COMPILE_DISABLE=1 \
        -v $DATA_ROOT/sft:/app \
        -v $MODEL_ROOT:/app/models \
        "$IMAGE" \
        python -u /app/scripts/generate_candidates_single_gpu.py \
            --gpu-id 0 \
            --start-idx "$start_idx" \
            --end-idx "$end_idx" \
            --input "$INPUT_FILE" \
            --output "$output_file" \
            --model "$MODEL_PATH" \
            --base-model "$BASE_MODEL"

    echo "  容器 $container_name 已启动"
}

# 函数：查看状态
show_status() {
    echo "========================================"
    echo "8 卡并行候选生成状态"
    echo "========================================"

    for gpu_id in $(seq 0 $((NUM_GPUS - 1))); do
        local container_name="${CONTAINER_PREFIX}${gpu_id}"
        local output_file="$DATA_ROOT/sft$DATA_ROOT/dpo/candidates_gpu${gpu_id}.json"

        # 容器状态
        local status=$(docker ps -a --filter "name=^${container_name}$" --format '{{.Status}}' 2>/dev/null || echo "不存在")

        # 进度
        local progress="0"
        if [ -f "$output_file" ]; then
            progress=$(python3 -c "import json; print(len(json.load(open('$output_file'))))" 2>/dev/null || echo "0")
        fi

        local expected=$SAMPLES_PER_GPU
        if [ $gpu_id -eq $((NUM_GPUS - 1)) ]; then
            expected=$((TOTAL_SAMPLES - gpu_id * SAMPLES_PER_GPU))
        fi

        printf "GPU %d: %3d/%3d (%s)\n" "$gpu_id" "$progress" "$expected" "$status"
    done

    echo "========================================"

    # GPU 使用情况
    echo ""
    echo "GPU 使用情况:"
    nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits | \
        while IFS=, read -r idx util mem_used mem_total; do
            printf "  GPU %s: %3s%% 利用率, %5s/%5s MiB\n" "$idx" "$util" "$mem_used" "$mem_total"
        done
}

# 函数：查看日志
show_logs() {
    local gpu_id=$1
    local container_name="${CONTAINER_PREFIX}${gpu_id}"

    if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
        docker logs -f "$container_name"
    else
        echo "容器 $container_name 不存在"
    fi
}

# 函数：停止所有任务
stop_all() {
    echo "停止所有候选生成任务..."
    for gpu_id in $(seq 0 $((NUM_GPUS - 1))); do
        local container_name="${CONTAINER_PREFIX}${gpu_id}"
        if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
            echo "  停止 $container_name..."
            docker rm -f "$container_name" >/dev/null 2>&1 || true
        fi
    done
    echo "完成"
}

# 函数：合并结果
merge_results() {
    echo "合并 8 卡结果..."
    python3 $DATA_ROOT/sft/scripts/merge_candidates.py
}

# 主逻辑
case "${1:-}" in
    status)
        show_status
        ;;
    logs)
        if [ -z "${2:-}" ]; then
            echo "用法: $0 logs <gpu_id>"
            exit 1
        fi
        show_logs "$2"
        ;;
    stop)
        stop_all
        ;;
    merge)
        merge_results
        ;;
    *)
        # 启动指定范围的 GPU
        start_gpu_id=${1:-0}
        end_gpu_id=${2:-$((NUM_GPUS - 1))}

        echo "========================================"
        echo "启动 GPU $start_gpu_id - $end_gpu_id 候选生成"
        echo "总样本: $TOTAL_SAMPLES"
        echo "每卡样本: $SAMPLES_PER_GPU"
        echo "========================================"

        for gpu_id in $(seq "$start_gpu_id" "$end_gpu_id"); do
            start_gpu "$gpu_id"
        done

        echo ""
        echo "所有任务已启动!"
        echo "使用以下命令查看状态:"
        echo "  $0 status"
        echo "  $0 logs <gpu_id>"
        ;;
esac
