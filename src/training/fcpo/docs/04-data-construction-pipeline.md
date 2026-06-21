# Preference Pair Construction Pipeline (V4 Standard Process)

**Created**: 2026-03-29
**Last Updated**: 2026-03-29 (Confirmed Plan 2: Independent Scoring + Image + Source Data)

---

## 0. Design Decisions

| Decision | Choice | Rationale |
|------|------|------|
| Scoring Method | **Independent Scoring** (non-comparative) | FCPO requires absolute scores; no label leakage; avoids position bias |
| Judge Input | **Image + Source Data + Candidate Text** | Image validates visual descriptions, source data validates precise numbers |
| Judge Model | gemini-3-flash | Stronger than flash-lite, consistent with V1 pair selection model |
| Training Format | No system prompt + unified Chinese prompt | Consistent with V1 DPO and SFT training format |

---

## 1. V1 vs T0.6 Comparison (Why V1 Works but T0.6 Doesn't)

| | V1 Original 1700 ✅ | T0.6 New 1115 ❌ |
|---|---|---|
| **Judge Model** | gemini-3-flash (strong) | gemini-2.5-flash-lite (weak) |
| **Selection Method** | **Comparative Selection**: 6 candidates + GT + image given to Judge together | **Independent Scoring**: Each candidate scored separately, take max/min |
| **Rejected Strategy** | **Hard-negative**: Deliberately select "looks professional but has factual errors" | Pure lowest score, no hard-negative concept |
| **Chosen Faithfulness** | 4.94 (near perfect) | 3.83 (far below V1's rejected) |
| **Format** | Unified Chinese prompt, no system prompt | Mixed English-Chinese prompt, has system prompt |
| **Result** | LF-2 = 0.755 | After merge 0.745, degraded by 1% |

**Core Difference**: V1 uses strong Judge for comparative selection + hard-negative, T0.6 uses weak Judge for independent scoring.

---

## 2. V4 Standard Pipeline

### Step 1: Candidate Generation

**Model**: SFT checkpoint (exp-012/checkpoint-640, LoRA rank=256)
**Generate 6 candidates per image**:
- Candidate 0: greedy decoding (do_sample=False)
- Candidates 1-5: sampling (temperature=0.9, top_p=0.95, top_k=50)

```bash
# Execute on server (pku-246 or H20)
python generate_candidates_single_gpu.py \
  --input data/images_to_process.json \
  --output data/candidates.json \
  --model /share4/yzy/models/qwen3-vl-8b-instruct \
  --adapter /share2/ww/qwen3vl-dpo/sft-checkpoint/exp-012-ckpt640 \
  --max-new-tokens 2048 \
  --num-samples 5 \
  --temperature 0.9 --top-p 0.95 --top-k 50
```

**Input format** (each entry needs image path + ground_truth):
```json
{
  "index": 0,
  "image": "images/xxx.png",
  "messages": [...],
  "ground_truth": "Reference standard summary text...",
  "_source": "V4"
}
```

### Step 2: Independent Fact Scoring (V4 New Approach)

**Script**: `qwen3vl-dpo-v4/scripts/score_candidates.py`
**Judge Model**: `gemini-3-flash-preview-nothinking`
**Method**: Each candidate **scored independently** — Judge sees 1 candidate + source data JSON + image

```bash
python scripts/score_candidates.py \
  --candidates data/candidates.json \
  --source-facts ../qwen3vl-dpo-v2/data/source_facts.json \
  --image-base $DATA_ROOT/sft/data \
  --max-workers 8
```

**Judge Input**:
- Image (base64) — validates visual/structural descriptions
- Source data (JSON) — validates precise numbers (if available)
- Candidate text — to be evaluated

**Judge Output** (independent per candidate):
```json
{
  "score": 78,
  "errors": ["Peak date is incorrect, actual is 2024-03 not 2024-07"],
  "reasoning": "Most claims accurate but one significant date error"
}
```

### Step 3: Construct Preference Pairs + Format Conversion

**Script**: `qwen3vl-dpo-v4/scripts/build_dpo_pairs.py`

```bash
python scripts/build_dpo_pairs.py \
  --scores data/scored_candidates.json \
  --candidates data/candidates.json \
  --min-delta 5 \
  --output data/dpo_v4.json
```

**Selection Logic**:
- chosen = highest fact_score among 6 candidates
- rejected = lowest fact_score among 6 candidates
- delta = chosen_score - rejected_score, skip if below threshold

**Unified Format** (consistent with V1 DPO + SFT training):
- **No system prompt**
- **Unified user prompt**: `<image>\nPlease analyze this financial chart in detail.`
- LlamaFactory sharegpt format

```json
{
  "conversations": [
    {"from": "human", "value": "<image>\nPlease analyze this financial chart in detail."}
  ],
  "chosen": {"from": "gpt", "value": "..."},
  "rejected": {"from": "gpt", "value": "..."},
  "images": ["images/xxx.png"]
}
```

**Attached _meta** (for analysis, not used in training):
```json
{
  "_meta": {
    "chosen_score": 85,
    "rejected_score": 42,
    "delta": 43,
    "chosen_errors": [],
    "rejected_errors": ["Peak date error"],
    "has_source_facts": true
  }
}
```

---

## 3. Data Source Inventory

### Available Image Pool

| Source | Count | Has Ground Truth | Has Source Data (verifiable) | Used for DPO |
|------|------|----------------|-----------------|-----------|
| V1 DPO Used | 1,700 | ✅ | 72% | ✅ Used |
| T0.6 Generated Candidates | 1,280 | ✅ | Partial | ⚠️ Has candidates, needs re-pairing |
| SFT Remaining | ~3,800 | ✅ | Partial | ❌ Unused |

### Expansion Plans

**Plan A (Quick): Re-pair T0.6's 1,280 images**
- Already has 6 candidates (`t06_candidates_1280.json`), no need to regenerate
- Only need to re-pair using V1's Judge process (gemini-3-flash comparative selection)
- Expected: ~1,100 new preference pairs, API cost for 1,280 calls
- Time: ~2 hours (8 concurrent)

**Plan B (Complete): Generate from SFT remaining 3,800 images**
- Need to generate candidates on GPU first (~6-12 hours on 8×3090)
- Then pair using V1 Judge process
- Expected: ~3,000 new preference pairs

**Plan C (A+B): Do both**
- Total ~4,000+ new preference pairs
- Plus original 1,700 = ~5,700 pairs

---

## 4. Fact-Guided Enhancement (Optional, Add After Step 2)

For preference pairs selected in Step 2, use r_fact v2 (gemini-3-flash 1-100 scoring) for secondary verification:

1. If r_fact finds chosen has more factual errors than rejected → **Flip** (swap chosen/rejected)
2. If |delta_r_fact| > 0.2 → mark as high-signal sample
3. During training, can use only high-signal subset, or give higher weight to high-signal samples

**Note**: This step is enhancement, not replacement. Step 2's Judge comparative selection is core.

---

## 5. Training Configuration (Fixed, Consistent with LF-2)

| Parameter | Value |
|------|-----|
| Framework | LlamaFactory 0.9.5 |
| loss | sigmoid DPO |
| β | 0.1 |
| lr | 1e-5 |
| LoRA rank | 256 |
| epochs | 1 |
| batch_size | 8 |
| DeepSpeed | ZeRO-2 |
| SFT adapter | exp-012/checkpoint-640 |

---

## 6. Key File Index

| Script | Path | Purpose |
|------|------|------|
| Candidate Generation | `qwen3vl-dpo/scripts/generate_candidates_single_gpu.py` | Step 1 |
| Judge Pairing | `qwen3vl-dpo/scripts/select_preference_pairs.py` | Step 2 |
| Format Conversion | `qwen3vl-dpo/scripts/convert_to_dpo_format.py` | Step 3 |
| T0.6 Candidates (existing) | `qwen3vl-dpo-v2/data/t06_candidates_1280.json` | Input for Plan A |
