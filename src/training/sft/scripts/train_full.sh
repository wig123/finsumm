#!/bin/bash
# 完整训练: 使用 8 卡进行 LoRA SFT
# 运行时间取决于数据量，预计 1-2 小时

set -e

echo "🚀 开始完整训练..."

# 切换到工作目录
cd /app

# RTX 4090 需要禁用 P2P
export NCCL_P2P_DISABLE=1
export NCCL_IB_DISABLE=1
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

# 8 卡训练（PyPI 版 LLaMA-Factory 直接使用 dataset_info.json 路径）
echo "🚀 启动 8 卡训练..."
FORCE_TORCHRUN=1 llamafactory-cli train /app/configs/qwen3vl_lora_sft.yaml

echo "✅ 训练完成！"
echo "📁 模型保存在: /app/outputs/"
