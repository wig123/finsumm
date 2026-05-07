# DPO Data

## 仓库内文件

- `dataset_info.json` — LLaMA-Factory 数据集注册
- `dpo/dpo_train_1700.json` (8.2 MB) — DPO 主训练集，1700 条
- `dpo/dpo_val_299.json` (1.5 MB) — DPO 验证集
- `dpo/dpo_train_clean.json` (4.9 MB) — 清洗后的训练集（去格式残留）
- `preference/preference_pairs.json` (849 KB) — 偏好对原始格式

## 仅在 GPU 服务器保留（体积过大）

| 文件 | 体积 | GPU 路径 |
|------|------|----------|
| `candidates/candidates_2000.json` | 38 MB | `$DATA_ROOT/dpo/data/candidates/` |
| `sampled/sampled_*.json` | 5.5–19 MB×3 | `$DATA_ROOT/dpo/data/sampled/` |
| `dpo/dpo_train_all_clean.json` | 9.7 MB | `$DATA_ROOT/dpo$DATA_ROOT/dpo/` |
| `dpo/dpo_train_remaining*.json` | 4.8–5.5 MB×2 | `$DATA_ROOT/dpo$DATA_ROOT/dpo/` |
| 训练用图片 | — | `$DATA_ROOT/sft/data/images/` 共用 |

需要时使用 `gpu-pull.sh` 拉取。
