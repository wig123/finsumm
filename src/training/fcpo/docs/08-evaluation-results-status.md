## Current Status (Last Updated: 2026-03-30 05:30)

### Round 2 Complete Evaluation Results

| Model | Judge Score | Faithfulness | Completeness | Analysis | Conciseness |
|------|-----------|-------------|-------------|---------|------------|
| dpo_v1_fix | **0.7640** | **3.52** | 4.00 | 3.71 | 4.56 |
| dpo_merged_fix (R1) | 0.7612 | 3.50 | 4.00 | 3.69 | **4.57** |
| **fcpo_merged_r2** | 0.7573 | 3.43 | **4.01** | **3.73** | 4.50 |
| fcpo_merged_v2 | 0.7559 | 3.45 | 4.00 | 3.67 | 4.52 |
| dpo_merged_r2 | 0.7506 | 3.38 | 3.97 | 3.70 | 4.52 |
| dpo_t06_fix | 0.7488 | 3.44 | 3.98 | 3.63 | 4.51 |

### Key Findings

1. **FCPO margin weighting is effective**: FCPO R2 (0.7573) > DPO R2 (0.7506), +0.007
2. **FCPO R2 has highest Analysis score** (3.73), indicating fact-aware training improves analytical depth
3. **All model differences are within statistical noise** (L2 200 samples, p>0.05)
4. **Faithfulness is the bottleneck** (3.4-3.5), Completeness has reached ceiling (4.0)

### Completed
- [x] FCPO v2 training + inference + evaluation (0.7559)
- [x] T06 re-scoring (903 entries)
- [x] Round 2 data construction (DPO 2681 entries, FCPO 2552 entries)
- [x] DPO R2 training + inference + evaluation (0.7506)
- [x] FCPO R2 training + inference + evaluation (0.7573)
- [x] Case study: FCPO v2 vs DPO R1 (no significant difference, p=0.39)
- [x] Case study: DPO R2 vs DPO R1 (no significant difference, p=0.075)
- [x] Data construction pipeline review (passed, no issues)

### 248 Training Environment Issue Log
- **Root cause**: CUDA_VISIBLE_DEVICES=0,1,2,3 mapped CUDA devices 2,3 were actually occupied by another user (bzy)
- **Solution**: Only use CUDA_VISIBLE_DEVICES=0,1 (2×A800, 84GB free each)
- **Lesson learned**: transformers pip downgrade/upgrade was a misleading direction; the real issue was GPU resource contention

### To Analyze
- [ ] Comprehensive optimization direction analysis (subagent in progress)
- [ ] How to further improve faithfulness

### Comprehensive Analysis Conclusion (2026-03-30 06:00)

**Core finding**: All model differences are non-significant on L2 (200 samples). FCPO helps on the most difficult samples but overall p=1.0.

**Bottleneck**: faithfulness concentrated in finmme_200 (40% F≤2)

**Optimization directions** (ranked by expected gain):
1. Increase finmme domain training data
2. Re-select T06 pairs using V1 Judge pipeline
3. Explore rpo_alpha + early stopping
4. Best-of-N + Fact Reranking
5. FCPO adaptive improvements

### Currently Running
- 248: FCPO R2 beta=0.05 ablation (expected completion 06:30)

### Best-of-N Experiment Results (2026-03-30 08:50)

**Best-of-5 Oracle**:
- Judge Score: 0.8495 (+0.092 vs greedy 0.7573)
- Faithfulness: 4.10 (+0.66 vs 3.43)
- finmme_200: 0.820 (+0.110 vs 0.710)

**All simple reranking strategies failed**:
- Longest / Median / Consensus(Jaccard) / Random all ≈ greedy, no improvement
- Semantic-level signals (Fact Score / Judge) needed for reranking

**Conclusion**: BoN has huge potential but requires quality signals. This supports the FCPO paper's argument—the value of Fact Score as a reranking signal.

**Next step**: Validate reranking with Fact Score.
