# Qwen3-VL DPO Project

DPO (Direct Preference Optimization) training based on the SFT fine-tuned model (exp-012).

## Current Status (2024-12-19)

**DPO-EXP-001**: Training complete, evaluating
- Training Metrics: loss=0.488, accuracies=86.5%, margins=4.47
- Checkpoints: checkpoint-50/100/150
- Evaluation: FinMME-160 inference in progress

## AutoDL Environment

- **SSH**: `ssh -p <port> <user>@<REMOTE_HOST>`
- **Password**: `<SSH_PASSWORD>`
- **GPU**: 5×RTX 4090
- **Model**: `<REMOTE_DATA_ROOT>/models/qwen3-vl-8b-instruct`
- **DPO Output**: `<REMOTE_DATA_ROOT>/qwen3vl-dpo/outputs/dpo-exp001/`
- **Evaluation Directory**: `<REMOTE_DATA_ROOT>/finmme-benchmark/`

## Project Goals

Further optimize financial chart analysis capabilities through DPO, learning human preferences.

## Environment Dependencies

- **Base Model**: Qwen3-VL-8B-Instruct
- **SFT Model**: exp-012-ckpt640 (from qwen3vl-sft project)
- **GPU Server**: AutoDL 5×RTX 4090
- **Training Framework**: LLaMA-Factory 0.9.4.dev0

## Directory Structure

```
qwen3vl-dpo/
├── CLAUDE.md              # This file
├── scripts/               # DPO related scripts
│   ├── build_dpo_data.py              # Sampling script
│   ├── generate_candidates_single_gpu.py  # Single GPU candidate generation
│   ├── launch_8gpu_parallel.sh        # 8-GPU parallel launch
│   └── merge_candidates.py            # Result merging
├── data/
│   ├── sampled/           # Sampled data
│   │   └── sampled_2000.json          # 2000 sampled examples
│   └── candidates/        # Candidate results
│       └── candidates_2000.json       # 12000 candidates (6 per sample)
├── experiments/           # Experiment logs
└── configs/               # DPO training configs
```

## Data Sources

2000 samples proportionally sampled from `qwen3vl-sft/data/all_train.json` (5099 samples):

| Data Source | Count | Proportion | Description |
|---|---|---|---|
| v3_synthesis | 900 | 45.0% | Synthetic charts v3 (syn_v2_, syn_, prog_) |
| v4_synthesis | 534 | 26.7% | Synthetic charts v4 (syn_v4_, syn_v4f_) |
| fin-chart | 312 | 15.6% | Real financial report charts (mc_) |
| finmme | 254 | 12.7% | FinMME benchmark (finmme_) |

## Candidate Generation Configuration

- **Model**: exp-012-ckpt640 (LoRA merged)
- **Candidates per sample**: 6 (1 greedy + 5 sample)
- **Sampling parameters**: temperature=0.9, top_p=0.95, top_k=50
- **max_new_tokens**: 2048
- **attention**: SDPA (PyTorch 2.x)

## Experiment Plan

### Experiment A: top vs bottom (B1)
- chosen: Highest scoring candidate
- rejected: Lowest scoring candidate
- Characteristics: Large difference, easy to learn

### Experiment B: top vs hard-negative (B2)
- chosen: Highest scoring candidate
- rejected: Second highest scoring candidate
- Characteristics: Small difference, more refined

## DPO Training (Beta)

### Quick Test Configuration (dpo-001)
- **Number of samples**: 100 (randomly sampled from 2000 samples)
- **Preference pair construction**: greedy as chosen, random sample as rejected
- **Base model**: Continue training exp-012-ckpt640

### Start Training
```bash
# 1. Sync data to GPU server
scp $DATA_ROOT/sft/data/dpo_train_100.json gpu:$DATA_ROOT/sft/data/
scp $DATA_ROOT/sft/data/dataset_info.json gpu:$DATA_ROOT/sft/data/
scp $DATA_ROOT/sft/configs/qwen3vl_lora_dpo.yaml gpu:$DATA_ROOT/sft/configs/

# 2. Launch DPO training (8 GPUs)
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

# 3. View logs
ssh gpu "docker logs -f qwen3vl-dpo"
```

### Key Configurations
| Parameter | Value | Description |
|---|---|---|
| stage | dpo | DPO training |
| pref_beta | 0.1 | DPO beta parameter |
| pref_loss | sigmoid | Standard DPO loss |
| learning_rate | 5e-5 | Low learning rate |
| num_train_epochs | 3 | 3 epochs |

## Experiment Progress

### DPO-EXP-001: Baseline (Training Completed)
- **Data**: 999 preference pairs, A1+B2+C1 strategy
- **Configuration**: β=0.1, sigmoid loss, lr=5e-6
- **Results**: accuracies=86.5%, margins=4.47
- **Details**: `experiments/dpo-exp001_baseline.md`

### Experiments to Run
| ID | Name | Changes |
|----|------|------|
| 002 | Scale Data | 1700 train + 299 val |
| 003 | hinge_loss | pref_loss=hinge |
| 004 | lower_beta | β=0.05 |
| 005 | higher_lr | lr=1e-5 |

## Quick Commands

```bash
# Connect to AutoDL

# View training logs
tail -f <REMOTE_DATA_ROOT>/qwen3vl-dpo/outputs/dpo-exp001/trainer_log.jsonl

# 5-GPU inference
cd <REMOTE_DATA_ROOT>/finmme-benchmark && /root/miniconda3/bin/python dpo_inference_5gpu.py \
  --model-name dpo-exp001-ckpt150 \
  --lora-path <REMOTE_DATA_ROOT>/qwen3vl-dpo/outputs/dpo-exp001/checkpoint-150

# GPU status
nvidia-smi --query-gpu=index,memory.used --format=csv
```

## Related Projects

- SFT Training: `$DATA_ROOT/sft`
- Evaluation Benchmarks: `$DATA_ROOT/benchmark`
- Experiment Logs: `experiments/README.md`
