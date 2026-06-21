# Inference Parameter Configuration Guide

## Current Configuration (Option C: Pure Greedy Decoding)

### Script Parameters
```python
outputs = model.generate(
    **inputs,
    max_new_tokens=2048,
    do_sample=False  # Greedy decoding, deterministic output
)
```

### Configuration Rationale

1.  **Task Requirement**: To build a benchmark evaluation dataset.
2.  **Reproducibility**: Deterministic output is required for comparative analysis across multiple runs.
3.  **Fair Comparison**: Qwen2.5-VL and Qwen3-VL are compared under identical conditions.
4.  **Alignment with Ground Truth**: GPT-5 generated reference answers may also use deterministic parameters.

---

## Qwen-VL Official Recommended Parameters

### Scheme Comparison

| Scheme                               | do_sample | temperature | top_p | top_k | Applicable Scenarios              |
| :----------------------------------- | :-------- | :---------- | :---- | :---- | :-------------------------------- |
| **Option A: Official Recommendation (Sampling Mode)** | True      | 0.7         | 0.8   | 20    | Production environments, diverse outputs |
| **Option B: Low Temperature Sampling** | True      | 0.1         | 0.9   | 50    | Balance determinism and diversity |
| **Option C: Greedy Decoding (Current)** | False     | -           | -     | -     | Benchmarking, deterministic evaluation |

### Official Recommended Configurations

#### Instruct Model (Qwen3-VL-8B-Instruct)
```python
outputs = model.generate(
    **inputs,
    max_new_tokens=2048,
    do_sample=True,
    temperature=0.7,
    top_p=0.8,
    top_k=20,
    repetition_penalty=1.0,
    presence_penalty=1.5
)
```

#### Thinking Model (Inference Enhancement)
```python
outputs = model.generate(
    **inputs,
    max_new_tokens=4096,
    do_sample=True,
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    repetition_penalty=1.0,
    presence_penalty=0.0
)
```

---

## Parameter Details

### Core Parameters

| Parameter           | Type | Default | Description                                      |
| :------------------ | :--- | :------ | :----------------------------------------------- |
| **max_new_tokens**  | int  | 2048    | Maximum number of new tokens to generate.        |
| **do_sample**       | bool | False   | Whether to use sampling (False = greedy decoding). |
| **temperature**     | float| 1.0     | Controls randomness (effective only when `do_sample=True`). |
| **top_p**           | float| 1.0     | Nucleus sampling threshold (cumulative probability). |
| **top_k**           | int  | 50      | Top-K sampling (keeps the K tokens with the highest probability). |

### Advanced Parameters

| Parameter            | Type | Default | Description                                      |
| :------------------- | :--- | :------ | :----------------------------------------------- |
| **repetition_penalty** | float| 1.0     | Penalty for repeating tokens (>1.0 reduces repetition). |
| **presence_penalty** | float| 0.0     | Penalty for token presence (encourages new tokens). |
| **num_beams**        | int  | 1       | Beam search width (>1 enables beam search).      |
| **early_stopping**   | bool | False   | Whether to stop beam search early.               |

---

## Parameter Impact Analysis

### temperature

```
temperature = 0.1  →  Very deterministic output, close to greedy decoding
temperature = 0.7  →  Balances creativity and accuracy (official recommendation)
temperature = 1.0  →  Standard sampling
temperature = 1.5  →  Highly random, may produce unreasonable output
```

**Financial Chart Analysis Recommendation**: 0.6-0.8

### top_p (Nucleus Sampling)

```
top_p = 0.5   →  Only considers tokens in the top 50% cumulative probability
top_p = 0.8   →  Official recommendation
top_p = 0.95  →  Thinking model recommendation
top_p = 1.0   →  Considers all tokens
```

### top_k (Top-K Sampling)

```
top_k = 1     →  Equivalent to greedy decoding
top_k = 20    →  Official recommendation
top_k = 50    →  More diverse
top_k = 0     →  Disable Top-K
```

---

## Warning Message Explanation

### Common Warnings

```
The following generation flags are not valid and may be ignored: ['temperature', 'top_p', 'top_k']
```

**Reason**: The internal implementation of Qwen3-VL's processor defaults to adding these parameters. However, these parameters are ineffective when `do_sample=False`.

**Impact**: ✅ **No Impact**. Greedy decoding is actually performed (`do_sample=False` has higher priority).

**Solution**:
1. Ignore the warning (Recommended).
2. Set environment variable: `export TRANSFORMERS_VERBOSITY=error`

---

## Recommended Configurations for Different Scenarios

### Benchmark Evaluation (Current Usage)
```python
max_new_tokens=2048,
do_sample=False
```
✅ Deterministic, Reproducible

### Production Environment
```python
max_new_tokens=2048,
do_sample=True,
temperature=0.7,
top_p=0.8,
top_k=20
```
✅ Balances accuracy and diversity

### Creative Generation
```python
max_new_tokens=4096,
do_sample=True,
temperature=1.0,
top_p=0.95,
top_k=50
```
✅ More diverse outputs

### Extremely Conservative
```python
max_new_tokens=2048,
do_sample=True,
temperature=0.1,
top_p=0.9,
top_k=10
```
✅ Close to deterministic while retaining sampling

---

## References

- [Qwen3-VL Official Documentation](https://github.com/QwenLM/Qwen3-VL)
- [Transformers Generation Parameters](https://huggingface.co/docs/transformers/main_classes/text_generation)
- [Context7 Qwen3-VL Documentation](https://context7.com/qwenlm/qwen3-vl)

---

## Modification History

- **2025-11-17**: Initial Configuration (Option C: Pure Greedy Decoding)
  - Removed `temperature=0.7` (conflicts with `do_sample=False`).
  - Only kept `max_new_tokens=2048, do_sample=False`.
  - Reason: To build a benchmark dataset requiring deterministic output.

---
