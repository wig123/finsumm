# V4 Experiment Plan: New Directions from FCPO Lessons Learned

**Creation Date**: 2026-03-29
**Prerequisites**: `00-fcpo-experiment-review.md`

---

## I. V4 Objectives

Building on the lessons from V2/V3 FCPO experiments, explore methods that can **truly leverage source data verifiability**.

### Confirmed Facts (Cannot Be Ignored)

| Fact | Supporting Data |
|------|-----------------|
| Standard DPO (β=0.1, rank=256) slightly outperforms SFT | LF-2=0.755 vs SFT=0.744 (+1.5%) |
| FCPO per-sample margin is ineffective | Shuffle ≈ FCPO, LF-FCPO all below SFT |
| r_fact v2 (3-flash 1-100) signal is better than v1 | v2: 56% positive, 21% tie vs v1: 39% positive, 42% tie (Tier1/2 only) |
| r_fact v1/v2 direction consistency is only 47% | LLM fact scoring is inherently noisy |
| T0.6 augmented data actually lowered scores | merged_2815=0.745 < original 1700=0.755, **reason to be investigated** |
| ms-swift inference is unreliable | mode collapse, 0.630 vs LF 0.755 |
| LlamaFactory inference is reliable | Reasonable score distribution, consistent with SFT |

### Key Questions for V4

> **If the r_fact signal is too weak to be injected into the loss, what is it suitable for?**

---

## II. Candidate Solutions (Prioritized)

### Solution A: Best-of-N + Fact Reranking (Utilize Fact Signal at Inference)

**Core Idea**: No training modification; use r_fact for reranking during inference.

```
SFT/DPO model → generate N candidates → r_fact + r_quality scoring → select the best
```

**Why it might work**:
- The absolute value of r_fact within a single sample might have discriminative power (among multiple candidates within chosen).
- The Δr_fact during training is small because both chosen and rejected come from the same SFT model, with limited differences.
- The diversity of N candidates during inference is greater, and the discriminative power of the fact signal might be better.

**Experimental Design**:
1. Generate N=8 candidates using the SFT model + temperature=0.7.
2. Score using r_fact (rule extraction + raw.csv verification).
3. Score using r_quality (Judge score).
4. Combined reranking: `score = α × r_fact + (1-α) × r_quality`
5. Comparison: Best-of-1 (greedy) vs Best-of-N (random) vs Best-of-N (r_fact) vs Best-of-N (r_quality) vs Best-of-N (combined).

**Advantages**: Zero training cost, directly validates the value of the fact signal.
**Risks**: N-fold inference cost.

### Solution B: Fact-Guided Data Selection (Filter Data with Fact Signal)

**Core Idea**: No loss modification; use r_fact to filter high-quality preference pairs for standard DPO.

```
1700 preference pairs → r_fact filtering → high-quality subset → standard DPO training
```

**Strategy Options**:
- B1: Remove samples where Δr_fact < -0.1 (chosen facts are worse, should not be positive examples).
- B2: Keep only samples where Δr_fact > 0.1 (high signal subset).
- B3: Sort by r_fact_chosen and keep only top-K (ensure chosen quality is high).

**Why it might work**:
- In V3 experiments, clean-B-fixed (846 cleaned samples) = 0.746, close to 1700 samples' 0.755.
- This indicates that removing "bad data" does not result in significant loss, and there might be room for improvement.

**Risks**: Reduced data volume, potentially worse than full-dataset DPO.

### Solution C: DPO Data Augmentation + Quality Control

**Core Idea**: Improve DPO effectiveness itself, without relying on the fact signal.

```
Current 1700 pairs → augment to 3000-5000 pairs → standard DPO
```

**Methods**:
- C1: Generate new preference pairs using remaining charts from SFT (3399 out of 5099 SFT charts not used for DPO).
- C2: Multi-model candidates (generate candidates using different checkpoints to increase diversity).
- C3: Quality-tiered DPO (group by Judge score difference, learn large differences first, then small ones).

### Solution D: SimPO / Other DPO Variants

**Core Idea**: Replace the loss function with a better one on top of standard DPO.

| Variant | Tested | Result |
|---------|--------|--------|
| Standard DPO (sigmoid) | ✅ | LF-2=0.755 (best) |
| SimPO | ✅ | h20_simpo=0.716 (poor) |
| β=0.05 | ✅ | 0.726-0.741 |
| β=0.2 | ✅ | 0.752 |
| 2 epoch | ✅ | Risk of overfitting |

SimPO has been tested and performed poorly. Other untested variants:
- D1: IPO loss
- D2: KTO (does not require preference pairs)
- D3: ORPO
- D4: DPO + SFT auxiliary loss (rpo_alpha)

### Solution E: Abandon FCPO Narrative, Shift to DPO Data Quality Research

**Core Idea**: Shift the paper's narrative from "modifying loss" to "modifying data".

> "In the field of financial chart structured summarization, the quality and source of DPO data are more important than the choice of preference optimization algorithm."

Ablation experiments required:
- Data volume ablation (500/1000/1700/3000)
- Data source ablation (synthetic vs. real)
- Preference pair construction method ablation (Judge scoring vs. Fact-guided vs. Random)
- Judge model ablation (preference pairs constructed by different Judges)

---

## III. Recommended Execution Order

```
Phase 1: Solution A (Best-of-N)     ← Zero training cost, quickly validate fact signal value
         Solution B (Data Selection)  ← Low cost, 1-2 training experiments
         Can be parallelized

Phase 2: Decide based on Phase 1 results
         If A is effective → Deep dive into reranking + training combination
         If B is effective → Solution C data augmentation
         If both ineffective → Solution E shift narrative
```

---

## IV. Evaluation Criteria (V4 Upgrade)

### Must-Have Improvements

| Issue | V2/V3 | V4 Requirement |
|-------|-------|----------------|
| Sample Size | Primarily L2 (200) | Key experiments must run **L3 (1000)** |
| Statistical Tests | Not performed | **3 seeds + paired bootstrap** |
| Inference Framework | Mixed ms-swift + LF | **Unified LlamaFactory** |
| Cross-Judge Validation | Not performed | Top-3 experiments use **GPT-5 cross-validation** |

### Evaluation Process

```
L1 (training metrics) → eliminate obvious failures
L2 (200 samples) → filter top-K
L3 (1000 samples) × 3 seeds → statistical testing, write into paper
L4 (manual 50-100) → final validation
```

---

## V. Time Budget

| Phase | Task | Estimate |
|-------|------|----------|
| Phase 1a | Best-of-N Inference + Evaluation | 1-2 Days |
| Phase 1b | Data Selection Training + Evaluation | 1-2 Days |
| Phase 2 | In-depth analysis based on results | 3-5 Days |
| Phase 3 | L3 Statistical Tests + Paper Experiments | 2-3 Days |
| **Total** | | **7-12 Days** |

---
