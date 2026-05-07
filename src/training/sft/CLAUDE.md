# Qwen3-VL SFT 项目指南

## 环境概览

- **GPU服务器**: 8×RTX 4090, 驱动 550.x (支持 CUDA 12.4)
- **Docker镜像**: `qwen3vl-sft:cu124-lf` (PyTorch 2.6.0+cu124 + transformers 4.52.4 + LLaMA-Factory 0.9.4.dev0)
- **训练框架**: LLaMA-Factory 0.9.4.dev0 (GitHub 版本，支持 qwen3_vl 模板)

## 快速命令

### 8卡训练
```bash
ssh gpu "docker run -d --name qwen3vl-train \
  --gpus all --ipc=host --network=host \
  --env-file $DATA_ROOT/sft/.env \
  -e FORCE_TORCHRUN=1 \
  -v $DATA_ROOT/sft/data:/app/data \
  -v $DATA_ROOT/sft/configs:/app/configs \
  -v $DATA_ROOT/sft/outputs:/app/outputs \
  -v $MODEL_ROOT:/app/models \
  qwen3vl-sft:cu124-lf \
  llamafactory-cli train /app/configs/qwen3vl_lora_sft.yaml"
```

### 查看日志
```bash
ssh gpu "docker logs -f qwen3vl-train"
```

## 已解决问题

### 1. CUDA OOM (8卡训练)
**现象**: GPU 7 内存不足
**解决**: `per_device_train_batch_size: 1`, `gradient_accumulation_steps: 16`

### 2. 无中间验证
**现象**: `eval_steps: 50` 超过总步数，无中间 eval
**解决**: `eval_steps: 8`, `save_steps: 8` (根据总步数调整)

### 3. W&B 阻塞训练
**现象**: 容器无外网，wandb 重试导致阻塞
**解决**: `.env` 添加 `WANDB_MODE=offline`, `WANDB_DIR=/app/outputs`

### 4. 镜像版本选择
**推荐**: 使用 `qwen3vl-sft:cu124-lf` 镜像（PyTorch 2.6.0+cu124 + LLaMA-Factory 0.9.4.dev0）
**说明**: 支持 qwen3_vl 模板，已升级到 PyTorch 2.6

## W&B 日志同步

训练完成后，日志在 `$DATA_ROOT/sft/outputs/wandb/`

```bash
# 拉取到本地
scp -r gpu:$DATA_ROOT/sft/outputs/wandb/ ~/wandb-logs/

# 本地同步 (需 pip install wandb && wandb login)
wandb sync ~/wandb-logs/offline-run-xxx
```

## 实验管理

```
experiments/README.md      # 实验索引
experiments/_template.md   # 实验模板
experiments/exp-XXX_*.md   # 实验记录
configs/archived/          # 配置归档
```

**新实验流程**：
1. `cp experiments/_template.md experiments/exp-001_name.md`
2. `cp configs/qwen3vl_lora_sft.yaml configs/archived/exp-001.yaml`
3. 编辑实验记录，运行训练，更新索引

## 关键配置文件

| 文件 | 用途 |
|------|------|
| `.env` | 环境变量 (WANDB, NCCL) |
| `configs/qwen3vl_lora_sft.yaml` | 训练超参数 |
| `data/dataset_info.json` | 数据集注册 |
| `docker/Dockerfile` | 镜像定义 |
| `experiments/README.md` | 实验索引 |

## 目录映射

| 容器路径 | 宿主机路径 |
|----------|-----------|
| `/app/data` | `$DATA_ROOT/sft/data` |
| `/app/configs` | `$DATA_ROOT/sft/configs` |
| `/app/outputs` | `$DATA_ROOT/sft/outputs` |
| `/app/models` | `$MODEL_ROOT` |
