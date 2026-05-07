# Qwen3-VL DPO 项目

基于 SFT 微调模型 (exp-012) 进行 DPO (Direct Preference Optimization) 训练。

## 当前状态 (2024-12-19)

**DPO-EXP-001**: 训练完成，评估中
- 训练指标: loss=0.488, accuracies=86.5%, margins=4.47
- Checkpoints: checkpoint-50/100/150
- 评估: 正在进行 FinMME-160 推理

## AutoDL 环境

- **SSH**: `ssh -p <port> <user>@<REMOTE_HOST>`
- **密码**: `<SSH_PASSWORD>`
- **GPU**: 5×RTX 4090
- **模型**: `<REMOTE_DATA_ROOT>/models/qwen3-vl-8b-instruct`
- **DPO输出**: `<REMOTE_DATA_ROOT>/qwen3vl-dpo/outputs/dpo-exp001/`
- **评估目录**: `<REMOTE_DATA_ROOT>/finmme-benchmark/`

## 项目目标

通过 DPO 进一步优化金融图表分析能力，学习人类偏好。

## 环境依赖

- **基座模型**: Qwen3-VL-8B-Instruct
- **SFT 模型**: exp-012-ckpt640 (来自 qwen3vl-sft 项目)
- **GPU 服务器**: AutoDL 5×RTX 4090
- **训练框架**: LLaMA-Factory 0.9.4.dev0

## 目录结构

```
qwen3vl-dpo/
├── CLAUDE.md              # 本文件
├── scripts/               # DPO 相关脚本
│   ├── build_dpo_data.py              # 抽样脚本
│   ├── generate_candidates_single_gpu.py  # 单卡候选生成
│   ├── launch_8gpu_parallel.sh        # 8卡并行启动
│   └── merge_candidates.py            # 结果合并
├── data/
│   ├── sampled/           # 抽样数据
│   │   └── sampled_2000.json          # 2000条抽样样本
│   └── candidates/        # 候选结果
│       └── candidates_2000.json       # 12000个候选 (6/样本)
├── experiments/           # 实验记录
└── configs/               # DPO 训练配置
```

## 数据来源

从 `qwen3vl-sft/data/all_train.json` (5099条) 按比例抽样 2000 条：

| 数据源 | 数量 | 比例 | 说明 |
|--------|------|------|------|
| v3_synthesis | 900 | 45.0% | 合成图表 v3 (syn_v2_, syn_, prog_) |
| v4_synthesis | 534 | 26.7% | 合成图表 v4 (syn_v4_, syn_v4f_) |
| fin-chart | 312 | 15.6% | 真实财报图表 (mc_) |
| finmme | 254 | 12.7% | FinMME benchmark (finmme_) |

## 候选生成配置

- **模型**: exp-012-ckpt640 (LoRA merged)
- **每样本候选数**: 6 (1 greedy + 5 sample)
- **采样参数**: temperature=0.9, top_p=0.95, top_k=50
- **max_new_tokens**: 2048
- **attention**: SDPA (PyTorch 2.x)

## 实验计划

### 实验 A: top vs bottom (B1)
- chosen: 最高分候选
- rejected: 最低分候选
- 特点: 差异大，易学习

### 实验 B: top vs hard-negative (B2)
- chosen: 最高分候选
- rejected: 次高分候选
- 特点: 差异小，更精细

## DPO 训练 (测试版)

### 快速测试配置 (dpo-001)
- **样本数**: 100 (从 2000 样本中随机抽取)
- **偏好对构建**: greedy 作为 chosen，随机 sample 作为 rejected
- **基座**: exp-012-ckpt640 继续训练

### 启动训练
```bash
# 1. 同步数据到 GPU 服务器
scp $DATA_ROOT/sft/data/dpo_train_100.json gpu:$DATA_ROOT/sft/data/
scp $DATA_ROOT/sft/data/dataset_info.json gpu:$DATA_ROOT/sft/data/
scp $DATA_ROOT/sft/configs/qwen3vl_lora_dpo.yaml gpu:$DATA_ROOT/sft/configs/

# 2. 启动 DPO 训练 (8卡)
ssh gpu "docker run -d --name qwen3vl-dpo \
  --gpus all --ipc=host --network=host \
  --env-file $DATA_ROOT/sft/.env \
  -e FORCE_TORCHRUN=1 \
  -v $DATA_ROOT/sft/data:/app/data \
  -v $DATA_ROOT/sft/configs:/app/configs \
  -v $DATA_ROOT/sft/outputs:/app/outputs \
  -v $MODEL_ROOT:/app/models \
  qwen3vl-sft:cu124-lf \
  llamafactory-cli train /app/configs/qwen3vl_lora_dpo.yaml"

# 3. 查看日志
ssh gpu "docker logs -f qwen3vl-dpo"
```

### 关键配置
| 参数 | 值 | 说明 |
|------|-----|------|
| stage | dpo | DPO 训练 |
| pref_beta | 0.1 | DPO beta 参数 |
| pref_loss | sigmoid | 标准 DPO loss |
| learning_rate | 5e-5 | 较低学习率 |
| num_train_epochs | 3 | 3 轮 |

## 实验进度

### DPO-EXP-001: Baseline (已完成训练)
- **数据**: 999 偏好对, A1+B2+C1 策略
- **配置**: β=0.1, sigmoid loss, lr=5e-6
- **结果**: accuracies=86.5%, margins=4.47
- **详情**: `experiments/dpo-exp001_baseline.md`

### 待运行实验
| ID | 名称 | 变更 |
|----|------|------|
| 002 | 扩大数据 | 1700 train + 299 val |
| 003 | hinge_loss | pref_loss=hinge |
| 004 | lower_beta | β=0.05 |
| 005 | higher_lr | lr=1e-5 |

## 快速命令

```bash
# 连接 AutoDL

# 查看训练日志
tail -f <REMOTE_DATA_ROOT>/qwen3vl-dpo/outputs/dpo-exp001/trainer_log.jsonl

# 5卡推理
cd <REMOTE_DATA_ROOT>/finmme-benchmark && /root/miniconda3/bin/python dpo_inference_5gpu.py \
  --model-name dpo-exp001-ckpt150 \
  --lora-path <REMOTE_DATA_ROOT>/qwen3vl-dpo/outputs/dpo-exp001/checkpoint-150

# GPU 状态
nvidia-smi --query-gpu=index,memory.used --format=csv
```

## 相关项目

- SFT 训练: `$DATA_ROOT/sft`
- 评估基准: `$DATA_ROOT/benchmark`
- 实验记录: `experiments/README.md`
