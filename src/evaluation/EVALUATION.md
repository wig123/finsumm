# LLM-Powered Evaluation System Usage Guide

## Overview

This evaluation system uses **Gemini 2.5 Flash** as the core evaluation engine, combined with traditional metrics (BLEU, ROUGE), for comprehensive evaluation of financial chart analysis text.

### Core Features

- ✅ **LLM-Powered**: Utilizes Gemini 2.5 Flash for intelligent evaluation, replacing complex rule matching.
- ✅ **Multimodal Support**: Directly analyzes chart images + text to verify grounding.
- ✅ **Low Cost**: $0.4 for 200 samples (approx. 2.8 RMB).
- ✅ **Concise Code**: Reduces code volume by 70% compared to traditional methods.
- ✅ **Comprehensive Coverage**: 13 core metrics covering all evaluation dimensions.

---

## Quick Start

### 1. Environment Setup

#### Install Dependencies

```bash
# Enter project directory
cd $DATA_ROOT/benchmark

# Install evaluation dependencies
pip install -r requirements-eval.txt
```

#### Configure API Key

```bash
# Set API Yi API Key (for Gemini 2.5 Flash)
export OPENAI_API_KEY='your-api-key-here'

# Verify configuration
echo $OPENAI_API_KEY
```

> **Note**: API Yi uses an OpenAI-compatible API format but calls Gemini models.

---

### 2. Run Evaluation

#### Basic Usage

```bash
# Evaluate Qwen2.5-VL inference results
python3 evaluate.py --results outputs/qwen25_results.jsonl

# Evaluate Qwen3-VL inference results
python3 evaluate.py --results outputs/qwen3_results.jsonl
```

#### Advanced Options

```bash
# Limit evaluation sample count (for quick testing)
python3 evaluate.py --results outputs/qwen25_results.jsonl --limit 10

# Skip traditional metrics (use LLM evaluation only)
python3 evaluate.py --results outputs/qwen25_results.jsonl --skip-traditional

# Skip chart grounding evaluation (when images are unavailable)
python3 evaluate.py --results outputs/qwen25_results.jsonl --skip-grounding

# Specify output path
python3 evaluate.py \
  --results outputs/qwen25_results.jsonl \
  --output outputs/qwen25_evaluation.json

# Use CPU (when no GPU available)
python3 evaluate.py --results outputs/qwen25_results.jsonl --device cpu

# Calculate BERTScore (requires GPU, slower)
python3 evaluate.py --results outputs/qwen25_results.jsonl --use-bertscore
```

---

## Evaluation Metrics Explained

### LLM-Powered Metrics

#### 1. Numerical Accuracy

Uses Gemini to extract numerical values from text, followed by programmatic difference calculation.

**Metrics**:
- `numerical_f1`: Numerical exact match F1 (1% tolerance)
- `relaxed_accuracy`: Loose match accuracy (5% tolerance)

**Threshold**: `numerical_f1 >= 0.80`

#### 2. Chart Grounding

Leverages Gemini's multimodal capabilities to directly analyze chart images and verify if the text faithfully represents the chart content.

**Metrics**:
- `parent_precision`: PARENT-style grounding precision
- `grounding_score`: Overall grounding score (0-1)
- `hallucination_count`: Number of hallucinated statements

**Threshold**: `parent_precision >= 0.85`

#### 3. Entity Accuracy

Uses Gemini to extract financial entities (companies, dates, metrics, etc.) and calculates the F1 score.

**Metrics**:
- `entity_f1`: Entity match F1 score
- `entity_precision`: Entity precision
- `entity_recall`: Entity recall

**Threshold**: `entity_f1 >= 0.90`

#### 4. Comprehensive Quality

Uses Gemini for a 5-dimensional quality scoring (similar to G-Eval).

**Dimensions**:
- `factual_accuracy` (30%): Factual Accuracy (1-5 score)
- `structure_adherence` (20%): Structural Adherence (1-5 score)
- `insight_depth` (25%): Insight Depth (1-5 score)
- `language_quality` (15%): Language Quality (1-5 score)
- `information_completeness` (10%): Information Confinement (1-5 score)

**Threshold**: `structure_adherence >= 4.5`

---

### Traditional Metrics

#### 5. BLEU (SacreBLEU)

Used for the "Data Relationships" section to evaluate exact match.

**Metrics**:
- `bleu_1` ~ `bleu_4`: 1-4 gram BLEU scores

#### 6. ROUGE

Used for the "Core Insights" section to evaluate information coverage.

**Metrics**:
- `rouge1`: Unigram coverage
- `rouge2`: Bigram coverage
- `rougeL`: Longest common subsequence

#### 7. BERTScore (Optional)

Semantic similarity evaluation (requires GPU).

**Metrics**:
- `bertscore_f1`: BERT-based semantic F1 score

---

## Interpreting Evaluation Results

### Output File Structure

```json
{
  "summary": {
    "numerical_f1": 0.87,
    "relaxed_accuracy": 0.92,
    "parent_precision": 0.88,
    "entity_f1": 0.91,
    "overall_quality": 4.2,
    "factual_accuracy": 4.5,
    "structure_adherence": 4.8,
    "insight_depth": 3.8,
    "passes_numerical_threshold": true,
    "passes_grounding_threshold": true,
    "passes_entity_threshold": true,
    "passes_structure_threshold": true
  },
  "traditional_metrics": {
    "overall": {
      "bleu_4": 0.42,
      "rouge1": 0.65,
      "rouge2": 0.48,
      "rougeL": 0.58
    },
    "section_data_relationships": { },
    "section_core_insights": { }
  },
  "per_sample_metrics": [ ]
}
```

### Threshold Checks

The system automatically checks the following thresholds:

| Metric | Threshold | Description |
|------|------|------|
| Numerical F1 | ≥ 0.80 | Numerical error rate not exceeding 20% |
| PARENT Precision | ≥ 0.85 | Hallucination rate not exceeding 15% |
| Entity F1 | ≥ 0.90 | Entity accuracy not below 90% |
| Structure Score | ≥ 4.5 | Structural integrity score not below 4.5/5.0 |

---

## Performance and Cost

### Performance Estimation

- **Single Sample Evaluation Time**: Approx. 2-3 seconds (LLM call)
- **Total Time for 200 Samples**: Approx. 10-15 minutes (including traditional metrics)
- **Traditional Metrics Time**: Approx. 1-2 minutes (for 200 samples)

### Cost Estimation

#### Gemini 2.5 Flash (API Yi)

- **Input Price**: $0.075 / 1M tokens
- **Output Price**: $0.30 / 1M tokens

**Evaluation Cost for 200 Samples**:
- Numerical Extraction: 200 × 2 = 400 calls
- Entity Extraction: 200 × 2 = 400 calls
- Quality Evaluation: 200 calls
- Grounding Verification: 200 calls (multimodal)

**Total**: Approx. $0.4 (approx. 2.8 RMB)

---

## Frequently Asked Questions

### Q1: How to skip chart grounding evaluation?

A: Use the `--skip-grounding` parameter:

```bash
python3 evaluate.py --results outputs/qwen25_results.jsonl --skip-grounding
```

Applicable scenarios: When image files are unavailable or paths are incorrect.

### Q2: Evaluation is too slow, what can I do?

A: You can take the following measures:

1. **Skip Traditional Metrics**: `--skip-traditional`
2. **Skip BERTScore**: Do not use `--use-bertscore`
3. **Limit Sample Count**: `--limit 50` (for quick testing)

### Q3: API calls fail, what should I do?

A: The system has a built-in automatic retry mechanism (up to 3 times). If it still fails:

1. Check if the API Key is correct.
2. Check network connectivity.
3. Review the error message; it might be a rate limit issue.

### Q4: How to compare two models?

A: Evaluate them separately and then compare the JSON results:

```bash
# Evaluate Qwen2.5-VL
python3 evaluate.py \
  --results outputs/qwen25_results.jsonl \
  --output outputs/qwen25_eval.json

# Evaluate Qwen3-VL
python3 evaluate.py \
  --results outputs/qwen3_results.jsonl \
  --output outputs/qwen3_eval.json

# Compare results
python3 -c "
import json
qwen25 = json.load(open('outputs/qwen25_eval.json'))
qwen3 = json.load(open('outputs/qwen3_eval.json'))

print('Qwen2.5-VL:', qwen25['summary']['overall_quality'])
print('Qwen3-VL:', qwen3['summary']['overall_quality'])
"
```

---

## Technical Architecture

### Modular Design

```
evaluators/
├── __init__.py                # Module exports
├── gemini_client.py           # Gemini API client
├── numerical_llm.py           # Numerical accuracy evaluator
├── grounding_llm.py           # Chart grounding evaluator
├── quality_llm.py             # Comprehensive quality evaluator
├── entity_llm.py              # Entity accuracy evaluator
└── traditional.py             # Traditional metrics evaluator
```

### Evaluation Workflow

```
Load inference results (JSONL)
    ↓
Single sample evaluation (4 evaluators in parallel)
    ├─ Numerical accuracy evaluation
    ├─ Chart grounding evaluation
    ├─ Entity accuracy evaluation
    └─ Comprehensive quality evaluation
    ↓
Traditional metrics evaluation (BLEU, ROUGE)
    ↓
Aggregate statistics + threshold checks
    ↓
Save results (JSON)
```

---

## Next Steps

1. Wait for inference to complete.
2. Fetch inference results: `./gpu-pull.sh`
3. Run evaluation: `python3 evaluate.py --results outputs/qwen25_results.jsonl`
4. Analyze results and compare the performance of Qwen2.5-VL and Qwen3-VL.

---

## References

- [Gemini API Documentation](https://ai.google.dev/docs)
- [SacreBLEU](https://github.com/mjpost/sacrebleu)
- [ROUGE Score](https://github.com/google-research/google-research/tree/master/rouge)
- [BERTScore](https://github.com/Tiiiger/bert_score)
- [PARENT (Dhingra et al., 2019)](https://arxiv.org/abs/1906.01081)
- [G-Eval (Liu et al., 2023)](https://arxiv.org/abs/2303.16634)

---
