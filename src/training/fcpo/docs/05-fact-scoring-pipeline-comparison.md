# Fact Scoring Pipeline Comparison and Issue Diagnosis

**Created**: 2026-03-29

---

## Your Intuition (Correct Logic)

```
Source data (raw.csv / data_summary.txt)
    ↓
Judge compares against source data, scores factual accuracy of chosen/rejected
    ↓
Δr_fact = r_fact_chosen - r_fact_rejected
```

**This logic is correct.** The problem is: there are actually 4 different pipelines, some implemented correctly, some incorrectly.

---

## Comparison of Four Pipelines

### Pipeline ① `compute_r_quality.py` (❌ Completely Wrong)

```
chosen/rejected text → gemini-flash-lite scoring (no image, no source data) → 1-5 score
```

| Issue | Details |
|------|------|
| **No source data** | Judge is told "you cannot see the chart, don't deduct points for potentially incorrect numbers" |
| **Evaluates writing quality** | Only checks internal text consistency and structure, doesn't verify data correctness |
| **Result** | chosen=4.94, rejected=4.89 (both near perfect, no discrimination) |
| **Impact** | FCPO's r_quality component ≈ 0, formula degrades to pure r_fact |

### Pipeline ② `compute_r_fact.py` + `verify_facts.py` (⚠️ Correct logic but noisy)

```
Step 1: extract_source_facts.py
        raw.csv / data_summary.txt → structured source_facts.json
        (rule extraction: statistics, extrema, trends, time ranges)

Step 2: LLM extracts factual claims from chosen/rejected text
        "peak in 2023-07 reached 8.5" → {type: extremum, value: 8.5, date: 2023-07}

Step 3: verify_facts.py rule matching
        claims vs source_facts, tolerance matching (numerical ±3%/±5%/±15%)
        → fact_precision = verified / (verified + falsified)

Step 4: compute_r_fact.py
        delta_r_fact = fact_precision_chosen - fact_precision_rejected
```

| Advantages | Defects |
|------|------|
| ✅ Has source data reference | ❌ Claims extraction depends on LLM, missing/incorrect extractions |
| ✅ Rule-based verification is deterministic | ❌ Can only verify numbers/extremes/trends, not complex reasoning |
| ✅ No LLM scoring noise | ❌ 1189/1700 valid (33 extraction failures, 478 Tier3 without source data) |
| | ❌ mean\|Δ\|=0.145, weak signal |

### Pipeline ③ `compute_r_fact_llm.py` v1 (⚠️ Correct logic but low discrimination)

```
source_facts.json + chosen text → gemini-flash-lite → 1-10 score
source_facts.json + rejected text → gemini-flash-lite → 1-10 score
delta = (chosen_score - rejected_score) / 10
```

| Advantages | Defects |
|------|------|
| ✅ **Has source data reference** | ❌ 1-10 scale too coarse, 42% samples have delta=0 (tie) |
| ✅ Independent scoring, no label leakage | ❌ flash-lite model is weak |
| ✅ Covers all Tier 1/2 | ❌ Only 39% positive signal |

### Pipeline ④ `compute_r_fact_llm_v2.py` v2 (✅ Currently best)

```
source_facts.json + chosen text → gemini-3-flash → 1-100 score
source_facts.json + rejected text → gemini-3-flash → 1-100 score
delta = (chosen_score - rejected_score) / 100
```

| Advantages | Defects |
|------|------|
| ✅ **Has source data reference** | ❌ v1/v2 directional consistency only 47% (high LLM scoring noise) |
| ✅ 1-100 fine-grained scale, ties reduced to 21% | ❌ Still 23% negative signal (delta<0) |
| ✅ Stronger model (3-flash) | |
| ✅ 56% positive signal (Tier 1/2) | |

---

## Core Issues Summary

| Issue | Status |
|------|------|
| r_quality (Pipeline ①) | **Completely invalid**, doesn't check source data, evaluates writing quality |
| r_fact rule-based (Pipeline ②) | Correct logic but claims extraction is bottleneck, weak signal |
| r_fact LLM v1 (Pipeline ③) | Correct logic but 1-10 scale too coarse |
| r_fact LLM v2 (Pipeline ④) | **Currently best**, but LLM scoring itself is noisy (v1/v2 consistency 47%) |

**FCPO formula**: `raw_margin = α × Δr_fact + (1-α) × Δr_quality`
- Because Δr_quality ≈ 0, effectively = `α × Δr_fact`
- And α itself decays by tier (Tier 2 × 0.6, Tier 3 = 0)
- Final effective signal is minimal

---

## What Should Be Done Correctly

**Your intuition is correct**: source data should be provided to the Judge to score model outputs based on source data. Pipeline ④'s logic is correct, but can be further improved:

### Improvement Directions

1. **Multiple scoring with averaging**: Score each sample 3 times, take average to reduce single-run LLM noise
2. **Use stronger models**: GPT-4o or Claude for fact checking (more expensive but more accurate)
3. **Show images to Judge**: Current Pipeline ④ only provides text + source_facts, not images. If images are provided, Judge can directly verify against charts
4. **Combine with rule-based verification**: Use rules for deterministic verification of numerical claims (Pipeline ②), use LLM for non-numerical claims, complementing each other
