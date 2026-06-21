# Server Resources

Inherited from V2, all configurations remain unchanged. For detailed documentation, see `$DATA_ROOT/dpo-v2/02-server-resources.md`.

---

## Server Overview

| Server      | GPU                     | SSH           | Framework                     | Purpose                     |
|-------------|-------------------------|---------------|-------------------------------|-----------------------------|
| **pku-246** | 8× RTX 3090 (24GB)      | `ssh <user>@<HOST_IP>` | ms-swift 4.0.2                | Hyperparameter Search, Training |
| **pku-247** | 8× RTX 3090 (24GB)      | `ssh <user>@<HOST_IP>` | LlamaFactory 0.9.5            | Inference, Candidate Generation |
| **pku-248** | 2×A40 + 4×A800 (80GB)   | `ssh <user>@<HOST_IP>` | LF 0.9.5 + ms-swift           | Shared, Large Rank Experiments |
| **pku-14**  | 6× L40 (44GB)           | `ssh <user>@<HOST_IP>` | ms-swift 4.0.2                | Shared, Auxiliary Training  |
| **Alibaba Cloud H20** | 8× H20 (96GB) | DLC CLI       | LlamaFactory (Custom Image) | Large-scale Experiments     |

## Key Paths

```bash
# Base model (NFS, shared across pku-246/247/248/14)
/share4/yzy/models/qwen3-vl-8b-instruct

# SFT checkpoint (NFS, mounted from pku-246)
/share2/ww/qwen3vl-dpo/sft-checkpoint/exp-012-ckpt640/

# DPO training data (pku-246 local)
/home/ww/qwen3vl-dpo$DATA_ROOT/dpo/dpo_train_1700.json
/home/ww/qwen3vl-dpo/data/images/  # 7677 images

# DLC CLI
$DATA_ROOT/dpo-v2/scripts/dlc

# Custom image (H20)
goalfyai-acr-registry-vpc.cn-beijing.cr.aliyuncs.com/goalfyinfra/llama-factory:v2
```

## Shared Machine Usage Rules

pku-248 and pku-14 are shared with other users:
1. Before starting, you must `nvidia-smi` to check occupancy.
2. You must use `CUDA_VISIBLE_DEVICES` to specify idle GPUs.
3. GPUs 4-5 on pku-248 belong to someone else (bzy) and cannot be used.
