# Qwen3-VL SFT Project Guide

## Environment Overview

- **GPU Server**: 8×RTX 4090, Driver 550.x (supports CUDA 12.4)
- **Docker Image**: `qwen3vl-sft:cu124-lf` (PyTorch 2.6.0+cu124 + transformers 4.52.4 + LLaMA-Factory 0.9.4.dev0)
- **Training Framework**: LLaMA-Factory 0.9.4.dev0 (GitHub version, supports qwen3_vl template)

## Quick Commands

### 8-GPU Training
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

### View Logs
```bash
ssh gpu "docker logs -f qwen3vl-train"
```

## Resolved Issues

### 1. CUDA OOM (8-GPU Training)
**Symptom**: GPU 7 out of memory
**Solution**: `per_device_train_batch_size: 1`, `gradient_accumulation_steps: 16`

### 2. No Intermediate Validation
**Symptom**: `eval_steps: 50` exceeds total steps, no intermediate eval
**Solution**: `eval_steps: 8`, `save_steps: 8` (adjust based on total steps)

### 3. W&B Blocking Training
**Symptom**: Container has no external network, wandb retries cause blocking
**Solution**: Add `WANDB_MODE=offline` to `.env`, `WANDB_DIR=/app/outputs`

### 4. Image Version Selection
**Recommended**: Use `qwen3vl-sft:cu124-lf` image (PyTorch 2.6.0+cu124 + LLaMA-Factory 0.9.4.dev0)
**Note**: Supports qwen3_vl template, upgraded to PyTorch 2.6

## W&B Log Sync

After training completes, logs are in `$DATA_ROOT/sft/outputs/wandb/`

```bash
# Pull to local machine
scp -r gpu:$DATA_ROOT/sft/outputs/wandb/ ~/wandb-logs/

# Sync locally (requires pip install wandb && wandb login)
wandb sync ~/wandb-logs/offline-run-xxx
```

## Experiment Management

```
experiments/README.md      # Experiment index
experiments/_template.md   # Experiment template
experiments/exp-XXX_*.md   # Experiment records
configs/archived/          # Configuration archive
```

**New Experiment Workflow**:
1. `cp experiments/_template.md experiments/exp-001_name.md`
2. `cp configs/qwen3vl_lora_sft.yaml configs/archived/exp-001.yaml`
3. Edit experiment record, run training, update index

## Key Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables (WANDB, NCCL) |
| `configs/qwen3vl_lora_sft.yaml` | Training hyperparameters |
| `data/dataset_info.json` | Dataset registration |
| `docker/Dockerfile` | Image definition |
| `experiments/README.md` | Experiment index |

## Directory Mapping

| Container Path | Host Path |
|----------------|-----------|
| `/app/data` | `$DATA_ROOT/sft/data` |
| `/app/configs` | `$DATA_ROOT/sft/configs` |
| `/app/outputs` | `$DATA_ROOT/sft/outputs` |
| `/app/models` | `$MODEL_ROOT` |
