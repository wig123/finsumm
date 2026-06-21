# DPO V4 Experiment Project

## Project Positioning

Based on lessons learned from V2/V3 FCPO experiments, explore methods that can truly leverage source data verifiability to provide experimental support for the ACMM 2026 paper.

**Your first step**: After reading this file, read in sequence:
1. `00-fcpo-experiment-review.md` — Complete lessons from V2/V3
2. `01-experiment-plan.md` — V4 approach and priorities
3. `02-server-resources.md` — SSH connection, paths, GPU status
4. `03-api-configuration.md` — All API keys

Then check current status (which tasks are completed, what's running on the server) and determine next actions.

---

## Core Context

### Confirmed Facts

| Fact | Data |
|------|------|
| SFT baseline (exp-012/ckpt-640) | L2=0.744 |
| Standard DPO best (LF-2, β=0.1, rank=256) | L2=0.755 |
| All FCPO ineffective | Shuffle ≈ FCPO, LF-FCPO < SFT |
| r_fact SNR=0.03 | 97% noise |
| ms-swift inference unreliable | mode collapse |
| LlamaFactory inference reliable | ✅ |

### Base Model and Data

- **Base model**: Qwen3-VL-8B-Instruct (`/share4/yzy/models/qwen3-vl-8b-instruct`)
- **SFT checkpoint**: exp-012/checkpoint-640 (LoRA rank=256)
- **DPO data**: 1700 preference pairs (pku-246: `/home/ww/qwen3vl-dpo$DATA_ROOT/dpo/`)
- **Images**: 7677 images (pku-246: `/home/ww/qwen3vl-dpo/data/images/`)
- **Training framework**: **LlamaFactory 0.9.5** (unified, no ms-swift)
- **Evaluation**: FinMME-1000, Judge=gemini-2.5-flash-lite

### Previous Projects

| Project | Path | Content |
|------|------|------|
| V1 (DPO original) | `../qwen3vl-dpo/` | Original DPO experiments |
| V2 (FCPO ms-swift) | `../qwen3vl-dpo-v2/` | FCPO pipeline + ms-swift experiments |
| V3 (FCPO LF) | `../qwen3vl-dpo-v3/` | LlamaFactory FCPO 17 experiments |
| SFT | `../qwen3vl-sft/` | SFT training |
| Evaluation framework | `../finmme-benchmark/` | FinMME evaluation |

---

## Behavioral Guidelines

### 1. Unified Use of LlamaFactory

No longer use ms-swift for DPO training and inference. All experiments unified on LlamaFactory 0.9.5.

### 2. Upgraded Evaluation Standards

- Critical experiments must run **L3 (1000 samples)**, not just L2 (200)
- Experiments for paper must use **3 seeds + paired bootstrap**
- Top-3 experiments use **GPT-5 cross Judge**

### 3. Complete Documentation

- Create MD for each experiment under `experiments/`
- Maintain `experiments/STATUS.md` global progress
- Place training configs in `configs/`

### 4. Inherit V2 General Rules

- Do not modify files from V1/V2/V3 projects
- Check GPU usage first on shared machines
- Test 10 samples before large-scale API calls
- Validate SSH commands on small scale first

---

## Directory Structure

```
qwen3vl-dpo-v4/
├── CLAUDE.md              # This file
├── 00-fcpo-experiment-review.md     # Complete lessons from V2/V3
├── 01-experiment-plan.md          # V4 approach
├── 02-server-resources.md        # Server configuration
├── 03-api-configuration.md           # API keys
├── experiments/            # Experiment records
│   └── STATUS.md           # Global progress
├── configs/                # Training configurations
├── scripts/                # Scripts
├── data/                   # Data
└── results/                # Evaluation results
```
