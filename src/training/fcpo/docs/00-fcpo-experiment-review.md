# FCPO Experiment Retrospective (V2/V3 Summary)

**Creation Date**: 2026-03-29
**Purpose**: To comprehensively document the entire process of FCPO (Fact-Calibrated Preference Optimization) from hypothesis to failure, providing decision-making basis for V4 experiments.

---

## I. Experimental Hypothesis

### 1.1 Core Insight

72% of charts in DPO training data are synthetically generated from code, retaining the complete source data (raw.csv / data_summary.txt). The source data can be used for **deterministic fact verification**, decomposing the reward signal into deterministic and probabilistic components:

$$r(x,y) = r_{\text{fact}}(x,y) + r_{\text{quality}}(x,y)$$

### 1.2 FCPO Loss

Injecting a per-sample fact-calibrated margin into the DPO sigmoid loss:

$$L_i = -\log \sigma(\beta \cdot \Delta\text{logits}_i - \gamma \cdot \Delta r_{\text{fact},i})$$

- `Δr_fact > 0`: Chosen fact is more accurate → increase margin → strengthen preference learning
- `Δr_fact < 0`: Rejected fact is more accurate → decrease/invert margin → weaken preference learning
- `Δr_fact = 0`: No fact signal (Tier 3 unverifiable data) → degenerates to standard DPO

### 1.3 Comparison Methods

| Method | Description | Signal Usage |
|------|------|------------|
| **FCPO** | Continuous margin: γ × Δr_fact | Applied to DPO logits |
| **FDPO** | Binary flip: swap chosen/rejected when Δr_fact < 0 | Data modification |
| **E-shuf** | Randomly shuffle Δr_fact assignment | Causal control |
| **Weight mode** | Margin as a multiplier instead of subtractor for logits | Scaling preference |

---

## II. Training Data

### 2.1 Original Preference Pairs: 1700

| Tier | Count | Percentage | Source | Verifiability |
|------|------|------|------|---------|
| Tier 1 (Fully Verifiable) | 832 | 48.9% | V4 (raw.csv) + V3 with original data | Any value, extreme values, trends |
| Tier 2 (Partially Verifiable) | 390 | 22.9% | V3 summary only | Extreme values, mean, trend direction |
| Tier 3 (Unverifiable) | 478 | 28.1% | fin-chart + finmme | No source data, margin=0 |

### 2.2 r_fact Construction Pipeline (6 Steps)

```
Step 1: build_source_mapping.py → source_mapping.json (1700 entries)
        Image filename → source data path + Tier classification

Step 2: T0.3 Fact Extraction (gemini-2.5-flash-lite)
        chosen/rejected response → extract factual claims → verify against source data
        → fact_scores.json (1189 valid entries)

Step 3: compute_r_fact.py → r_fact.json (1700 entries)
        r_fact = fact_precision = verifiable_correct / total_verifiable_claims
        delta_r_fact = r_fact_chosen - r_fact_rejected
        Tier 3: delta_r_fact = 0

Step 4: compute_r_quality.py → r_quality.json (1700 entries)
        Judge evaluation (excluding faithfulness dimension to avoid overlap with r_fact)
        Weights: completeness 46.2% + analysis 38.5% + conciseness 15.4%

Step 5: prepare_decomposed_data.py → dpo_decomposed_base.json
        Adaptive α: α_i = 0.5 × min(claim_count/10, 1.0) × tier_factor
        tier_factor: Tier 1 = 1.0, Tier 2 = 0.6, Tier 3 = 0.0
        raw_margin = α × Δr_fact + (1-α) × Δr_quality

Step 6: generate_fcpo_data.py → experiment variant JSONL files
        γ = 0.3 × mean_dpo_margins / mean_|Δr_fact|
          = 0.3 × 4.113 / 0.1451 = 8.5
```

### 2.3 r_fact Signal Quality (Fatal Weakness)

| Metric | Value | Meaning |
|------|-----|------|
| Samples with fact signal | ~72% (Tier 1+2) | 28% completely without signal |
| Δr_fact > 0 (chosen more accurate) | ~28% | Only 1/4 of samples have positive signal |
| Δr_fact = 0 (equal) | ~42% | Nearly half have no difference |
| Δr_fact < 0 (rejected more accurate) | ~19% | |
| mean \|Δr_fact\| | 0.1451 | Extremely small difference |
| **SNR (Signal-to-Noise Ratio)** | **~0.03** | **97% noise** |
| Δr_fact vs Δr_quality Pearson Correlation | 0.13-0.39 | Weak correlation between the two signals |
| Spearman Correlation of three fact methods | 0.13-0.39 | Fact verification itself is unstable |

**Core Problem**: The factual accuracy difference between most chosen/rejected pairs is extremely small, with the signal being drowned out by a large number of samples with Δ≈0.

---

## III. Training Process

### 3.1 Two Training Frameworks

| Framework | Platform | Implementation | Inference | Reliability |
|------|------|---------|------|--------|
| **ms-swift 4.0.2** | pku-246/247/248/14/H20 | monkey-patch DPOTrainer | SGLang | ❌ **mode collapse**, E0=0.630 |
| **LlamaFactory 0.9.5** | pku-248/H20 | Modified 5 source files | transformers | ✅ E0=0.755, results are credible |

**Key Finding**: ms-swift + SGLang inference has a systemic mode collapse issue. With the same data and training, ms-swift inference yields 0.630 vs LlamaFactory inference yields 0.755. **All ms-swift FCPO results are unreliable.**

### 3.2 ms-swift FCPO Experiment Results (V2 Project, β=0.05, Unreliable)

| Experiment | Judge | vs E0 | Method |
|------|-------|-------|------|
| **E1b (unclamped γ=8.5)** | 0.660 | +0.030 | additive unclamped |
| E0-control | 0.630 | baseline | standard DPO |
| E-shuf | 0.612 | -0.018 | shuffle control |
| E1d (Tier1/2) | 0.611 | -0.019 | clamped, Tier1/2 only |
| E1a (clamped γ=8.5) | 0.600 | -0.030 | additive clamped |
| E-fdpo | 0.593 | -0.037 | binary flip |
| E1c (weight) | 0.565 | -0.065 | multiplicative |

> ⚠️ E0=0.630 vs LF's 0.755 proves these results are affected by inference bugs, and the relative ranking may also be unreliable.

### 3.3 LlamaFactory FCPO Experiment Results

#### V3 Project (H20, β=0.1, r_fact v1/v2, L2=200 samples)

| Rank | Experiment | L2 Score | vs LF-2 | Notes |
|------|------|---------|---------|------|
| 1 | FDPO-v2 | 0.764 | +0.009 | ⚠️ Data bug: flip not actually implemented |
| 2 | FDPO-real-g4 | 0.762 | +0.007 | |
| 3 | FCPO-v2g4 | 0.762 | +0.007 | == FDPO-v2 data |
| 4 | FCPO-v1g2 | 0.756 | +0.001 | |
| 5 | **Shuffle-v2** | **0.756** | **+0.001** | ⚠️ Random margin has same effect |
| 6 | LF-2 (baseline) | 0.755 | — | Standard DPO |
| 7 | FCPO-v1g1 | 0.753 | -0.002 | |
| 8 | FCPO-v2g1 | 0.752 | -0.003 | |
| 9 | FCPO-v2g2 | 0.750 | -0.005 | |
| 10 | FCPO-v1g4 | 0.744 | -0.011 | Excessive γ is detrimental |

#### V2→LF Replication (pku-248, β=0.1, γ=8.5 unclamped, L2=200 samples)

| Experiment | Judge | vs SFT |
|------|-------|--------|
| LF-2 (standard DPO) | 0.755 | +0.011 |
| SFT baseline | 0.744 | — |
| lf_fcpo_ga16 | 0.729 | -0.015 |
| lf_fcpo_e1b | 0.727 | -0.017 |
| lf_fcpo_2epoch | 0.725 | -0.019 |
| lf_fcpo_beta005 | 0.718 | -0.026 |

---

## IV. Evaluation Process

| Level | Sample Size | Time | Purpose | Reliability |
|------|--------|------|------|--------|
| L1 | — | 0 | Initial screening of training metrics | Only excludes obvious failures |
| **L2** | **200** | ~30min | Main screening | ±1-2% fluctuation, insufficient to distinguish <1% differences |
| L3 | 1000 | ~2-3h | Final paper evaluation | Not performed for FCPO |
| L4 | 50-100 | — | Human evaluation | Not performed |

**Evaluation Configuration Fixed**:
- Judge: gemini-2.5-flash-lite, temperature=0
- Dimensions: Faithfulness 35% + Completeness 30% + Analysis 25% + Conciseness 10%
- Inference: greedy decoding, max_tokens=2048

**Problem**: Almost all FCPO conclusions are based on L2 (200 samples). The ±1-2% fluctuation in 200 samples is enough to mask the small differences of FCPO. L3 validation was not performed, nor was multi-seed statistical testing.

---

## V. Experimental Design Flaws

| Flaw | Impact |
|------|------|
| ms-swift inference mode collapse not discovered promptly | Numerous experimental conclusions are incorrect (E1b "effective" was an illusion) |
| Insufficient L2 sample size | CI of 200 samples > inter-experiment differences |
| FDPO-v2 data bug | Flip was never implemented, FDPO-v2 == FCPO-v2g4 |
| No multi-seed runs | Cannot distinguish true improvement from random fluctuation |
| γ dependency on specific experiments | γ=8.5 based on R1-03's mean_margins=4.113 |
| Unstable r_fact methods | Three fact evaluation methods correlated at 0.13-0.39 |

---

## VI. Conclusion: Why FCPO Doesn't Work

| Root Cause | Evidence |
|------|------|
| **r_fact signal is too weak** | SNR=0.03, mean\|Δ\|=0.145, 42% samples Δ=0 |
| **Fact method itself is unstable** | Three methods Spearman 0.13-0.39 |
| **Shuffle ≈ FCPO** | Shuffle=0.756 vs FCPO-v1g2=0.756 (no causal effect) |
| **All LF experiments are below DPO** | 4 LF-FCPO: 0.718-0.729 < SFT 0.744 < DPO 0.755 |
| **Large γ amplifies incorrect signals** | FCPO-v1g4=0.744 (γ=4 is worst) |
| **Preference pair quality differences are inherently small** | Chosen/rejected are both generated by SFT models, with limited quality differences |

---

## VII. Tracing the 0.764 Score in the Paper

The FCPO 0.764 in Paper Table 4 originates from `FDPO-v2`:
- **Evaluation Set**: L2 (200 samples), not L3 (1000 samples)
- **Data Bug**: FDPO-v2 data == FCPO-v2g4 data (flip not implemented)
- **Actual L3 Score**: Not run, but the maximum improvement on L2 for all V3 experiments was only +0.009
- **This score cannot be used in the paper**

---

## VIII. Optimization Directions for V4 Reference

### A. Improve r_fact Signal Quality (Root Problem)

| Scheme | Action | Expectation | Cost |
|------|------|------|------|
| A1. Stronger LLM Extraction | Use GPT-4o/Claude for fact extraction | More accurate claims | 1700×2 API calls |
| A2. Multi-Judge Voting | 3 LLMs independently extract + verify | Reduce randomness | 3x API calls |
| A3. High Signal Filtering | Use only samples with \|Δr_fact\| > threshold for FCPO | Reduce noise | Low |
| A4. Rule-based Numerical Claim Extraction | Regex matching numbers → compare with raw.csv | Deterministic verification | Medium |

### B. Improve Margin Injection Method

| Scheme | Action |
|------|------|
| B1. Adaptive γ per tier | Tier 1 large γ, Tier 2 small γ, Tier 3=0 |
| B2. Sample weight instead of margin | `weight = 1 + λ × |Δr_fact|` |
| B3. Two-stage training | Stage 1 standard DPO → Stage 2 FCPO high-signal subset |
| B4. SimPO + per-sample margin | No ref model needed, per-sample γ |

### C. Change Strategy

| Scheme | Action |
|------|------|
| C1. Best-of-N + Fact reranking | Use r_fact for reranking during inference (no training modification) |
| C2. Fact-guided data selection | Use r_fact to filter high-quality preference pairs for standard DPO |
| C3. DPO data augmentation | 1700 → 3000+, more preference pairs |
| C4. Negative results paper | Detailed analysis of why FCPO doesn't work |

---

## IX. Key File Index

### V2 Project (`$DATA_ROOT/dpo-v2/`)

| File | Description |
|------|------|
| `scripts/compute_r_fact.py` | r_fact calculation |
| `scripts/compute_r_quality.py` | r_quality calculation |
| `scripts/prepare_decomposed_data.py` | Merged + adaptive α |
| `scripts/generate_fcpo_data.py` | Generate experiment variants |
| `scripts/patches/deploy_dpo_margin.py` | TRL per-sample margin patch |
| `data/fcpo_gamma_config.json` | γ=8.5 configuration |
| `data/r_fact.json` | 1700 r_fact data |
| `data/r_quality.json` | 1700 r_quality data |
| `data/dpo_decomposed_base.json` | Merged decomposed data |
| `experiments/fcpo-interim-analysis.md` | ms-swift intermediate analysis (unreliable) |

### V3 Project (`$DATA_ROOT/dpo-v3/`)

| File | Description |
|------|------|
| `scripts/patch_fcpo.py` | LlamaFactory FCPO 4 file patch |
| `scripts/generate_fcpo_data.py` | V3 data generation (γ=1/2/4) |
| `HANDOFF-2026-03-23.md` | 17 experiments full ranking |
| `results/FCPO-*.json` | L2 evaluation results for each experiment |

### Dependent Projects

| Project | Path |
|------|------|
| DPO V1 | `$DATA_ROOT/dpo/` |
| SFT Project | `$DATA_ROOT/sft/` |
| Evaluation Framework | `$DATA_ROOT/benchmark/` |
