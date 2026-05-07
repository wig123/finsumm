#!/bin/bash
# Smoke Test: 快速验证环境和数据格式
# 运行约 5-10 分钟

set -e

echo "🔥 开始 Smoke Test..."

# 设置数据目录（pip 安装的 LLaMA-Factory 使用环境变量）
export LLAMAFACTORY_DATA_DIR=/app/data

# 检查数据文件
echo "📝 检查数据文件..."
if [ ! -f "/app/data/finmme_train.json" ]; then
    echo "❌ 错误: 找不到训练数据 /app/data/finmme_train.json"
    exit 1
fi

# 修改 dataset_info.json 中的路径（移除 finmme/ 前缀，因为数据就在 /app/data 根目录）
echo "📂 准备数据集配置..."
python3 << 'EOF'
import json

# 读取配置
with open("/app/data/dataset_info.json", "r") as f:
    config = json.load(f)

# 修正路径：数据文件直接在 /app/data 目录下，不在 finmme 子目录
for key in config:
    if "file_name" in config[key]:
        # 移除 finmme/ 前缀
        config[key]["file_name"] = config[key]["file_name"].replace("finmme/", "")

# 保存修正后的配置
with open("/app/data/dataset_info.json", "w") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)

print(f"✓ 数据集配置已准备好: {list(config.keys())}")
EOF

# 运行 smoke test（单卡）
echo "🚀 启动训练..."
CUDA_VISIBLE_DEVICES=0 llamafactory-cli train /app/configs/qwen3vl_lora_sft_smoke.yaml

echo "✅ Smoke Test 完成！"
