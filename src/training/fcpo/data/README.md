# FCPO Data

## Files in Repository (< 15 MB per file)

- `fcpo_merged.json` (12 MB) — FCPO Round 1 Merged Training Data
- `fcpo_merged_r2_aligned.json` (13 MB) — Round 2 Aligned Version (for final training)
- `fcpo_merged_v2_aligned.json` (13 MB) — v2 Pipeline Aligned Version
- `dpo_v1_2000.json` (8.4 MB) / `dpo_v1_train_aligned.json` (7.5 MB) — DPO v1 Data for Comparison
- `dpo_t06_1280.json` / `dpo_t06_r2.json` — DPO Subset of Candidate Generations with temperature 0.6
- `scored_*.json` — Fact Scoring Intermediate Product (for reproducing FCPO margin calculation)
- `source_mapping_all.json` (1.2 MB) — Chart → Source Data Mapping
- `smoke_test_v2_5.json` / `candidates_random20.json` — Small Scale Smoke Data

## Retained on GPU Server Only

| File | Size | GPU Path |
|------|------|----------|
| `source_facts_all.json` | 50 MB | `$DATA_ROOT/dpo-v4/data/` |
| `dpo_merged_with_meta.json` | 14 MB | `$DATA_ROOT/dpo-v4/data/` |
| `dpo_merged_r2_with_meta.json` | 15 MB | `$DATA_ROOT/dpo-v4/data/` |
| `dpo_merged_all.json` | 12 MB | `$DATA_ROOT/dpo-v4/data/` |
