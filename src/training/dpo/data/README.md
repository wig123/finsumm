# DPO Data

## Files in Repository

- `dataset_info.json` — LLaMA-Factory Dataset Registry
- `dpo/dpo_train_1700.json` (8.2 MB) — DPO main training set, 1700 entries
- `dpo/dpo_val_299.json` (1.5 MB) — DPO validation set
- `dpo/dpo_train_clean.json` (4.9 MB) — Cleaned training set (removed format artifacts)
- `preference/preference_pairs.json` (849 KB) — Preference pairs raw format

## Kept on GPU Server Only (Too Large)

| File | Size | GPU Path |
|------|------|----------|
| `candidates/candidates_2000.json` | 38 MB | `$DATA_ROOT/dpo/data/candidates/` |
| `sampled/sampled_*.json` | 5.5–19 MB×3 | `$DATA_ROOT/dpo/data/sampled/` |
| `dpo/dpo_train_all_clean.json` | 9.7 MB | `$DATA_ROOT/dpo$DATA_ROOT/dpo/` |
| `dpo/dpo_train_remaining*.json` | 4.8–5.5 MB×2 | `$DATA_ROOT/dpo$DATA_ROOT/dpo/` |
| Training Images | — | `$DATA_ROOT/sft/data/images/` Shared |

Use `gpu-pull.sh` to pull when needed.
