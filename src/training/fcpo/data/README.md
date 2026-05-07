# FCPO Data

## 仓库内文件（< 15 MB 单文件）

- `fcpo_merged.json` (12 MB) — FCPO 第一轮合并训练数据
- `fcpo_merged_r2_aligned.json` (13 MB) — 第二轮对齐版（最终训练用）
- `fcpo_merged_v2_aligned.json` (13 MB) — v2 流水线对齐版
- `dpo_v1_2000.json` (8.4 MB) / `dpo_v1_train_aligned.json` (7.5 MB) — 用于对比的 DPO v1 数据
- `dpo_t06_1280.json` / `dpo_t06_r2.json` — temperature 0.6 候选生成的 DPO 子集
- `scored_*.json` — Fact 评分中间产物（用于复现 FCPO margin 计算）
- `source_mapping_all.json` (1.2 MB) — 图表 → source 数据映射
- `smoke_test_v2_5.json` / `candidates_random20.json` — 小规模 smoke 数据

## 仅在 GPU 服务器保留

| 文件 | 体积 | GPU 路径 |
|------|------|----------|
| `source_facts_all.json` | 50 MB | `$DATA_ROOT/dpo-v4/data/` |
| `dpo_merged_with_meta.json` | 14 MB | `$DATA_ROOT/dpo-v4/data/` |
| `dpo_merged_r2_with_meta.json` | 15 MB | `$DATA_ROOT/dpo-v4/data/` |
| `dpo_merged_all.json` | 12 MB | `$DATA_ROOT/dpo-v4/data/` |
