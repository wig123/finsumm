# V4 Experiment Plan

**Created**: 2026-03-30

---

## Experiment Round 1 (Current, No Data Supplementation)

Using existing 2551 preference pairs (V1 1488 + T06 1063), 729 synthetic charts in T06 have no source_facts.

| Experiment | Data | Method | Margin Strategy | Status |
|------|------|------|-----------|------|
| DPO-T06 | T06 1063 | Standard DPO | — | ✅ 0.738 |
| DPO-V1 | V1 1488 | Standard DPO | — | ✅ 0.745 |
| DPO-Merged | V1+T06 2551 | Standard DPO | — | ✅ **0.761** |
| **FCPO-Merged-v2** | V1+T06 2551 | FCPO | With source=delta weighted, no source=1.0 | 🔄 Training |

### FCPO-Merged-v2 Margin Design

```
Data with source (832 items, 33%): margin = delta / mean_delta (range 0.51-3.74)
Data without source (1719 items, 67%): margin = 1.0 (standard DPO)

Loss: L_i = -log σ(β × margin_i × Δlogits_i)
```

---

## Experiment Round 2 (Supplement T06 source_facts)

Build source_mapping + extract source_facts for 729 synthetic charts in T06, then rerun the full pipeline.

### Step 1: Extend source_mapping

T06 synthetic chart filenames follow the same rules (syn_v2_XXX / syn_XXX / prog_XXX / syn_v4_XXX / syn_v4f_XXX), can directly map using V2's `build_source_mapping.py` logic.

```bash
# Extract synthetic chart image names from t06_candidates_1280.json
# Build image → source_path mapping (reuse V2's path rules)
# Output: source_mapping_t06.json
```

### Step 2: Extract source_facts

```bash
# Run extract_source_facts.py on the new 729 synthetic charts (parsing bug already fixed)
# Output: source_facts_t06.json
```

### Step 3: Re-score T06's 729 Synthetic Charts

```bash
# Use score_candidates.py to re-score only these 729 items (now with source_facts)
# Other samples remain unchanged
```

### Step 4: Rebuild Preference Pairs

T06's 729 synthetic charts need re-pairing (due to score changes), rest remain unchanged.

### Step 5: Retrain

| Experiment | Expected Change |
|------|---------|
| DPO-Merged-R2 | More accurate pairing for T06 synthetic charts → potential improvement |
| FCPO-Merged-R2 | Data with source increases from 832→~1560, FCPO coverage doubles |

---

## Unified Evaluation Protocol

All experiments use the same inference environment:
- **Server**: pku-246, 8×3090
- **Script**: `l2_dpo_inference.py`
- **MAX_PIXELS**: 1280×32×32 (current)
- **Prompt**: Short version (CN/EN)
- **Judge**: `l2_judge_eval.py`, gemini-flash-lite, with GT reference

### Baseline (Same Protocol)

| Model | L2 Score | Notes |
|------|---------|------|
| SFT baseline | 0.744* | Need to confirm same protocol |
| LF-2 (original DPO) | ? | Need to re-inference on 246 |

*SFT 0.744 from V3 project inference (pku server, `sft_only_diag`), likely same protocol but needs verification.

---

## Timeline

| Task | Estimated Time | Dependencies |
|------|---------|------|
| FCPO-Merged-v2 training | ~40min | 🔄 In progress |
| FCPO-Merged-v2 inference+eval | ~15min | Training complete |
| Build T06 source_mapping | ~10min | None |
| Extract T06 source_facts | ~5min | source_mapping |
| Re-score 729 items | ~30min | source_facts |
| Rebuild preference pairs | ~5min | Scoring complete |
| Round 2 DPO train+inference+eval | ~60min | Preference pairs |
| Round 2 FCPO train+inference+eval | ~60min | Preference pairs |
