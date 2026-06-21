# Feature: Evaluation - Chart Summarization Quality Evaluation

## Goal

- Evaluate the accuracy and completeness of model-generated summaries.
- Differentiate between three dimensions: numerical accuracy, semantic similarity, and data grounding.

## Evaluation Levels

| Level | Metric | Priority |
|------|------|--------|
| P0 | Numerical F1 (Numerical Accuracy) | Must |
| P0 | PARENT (Data Grounding) | Must |
| P1 | CIDEr (Key Information Coverage) | Recommended |
| P1 | Entity F1 (Entity Accuracy) | Recommended |
| P1 | BLEURT (Overall Quality) | Recommended |
| P2 | FactScore v2 | Optional |

## Inputs / Outputs

**Inputs**:
- Model-generated summary (prediction)
- Reference summary (reference)
- Chart image (chart.png)

**Outputs**: Evaluation scores + Fact-level diagnostics

## FactScore v2 Design

```
pred_facts → Compare with ref_facts
          → Match: Ref Match
          → No match: GPT-4 judges whether chart supports it
                  → Supported: Chart Support
                  → Not supported: Error
```

**Key Decisions**:
- Use rule-based calculations for numerical comparison (to avoid model errors).
- Differentiate between two types of correctness: "reference match" and "chart supported".

## Constraints

- Numerical tolerance: 1% for exact values, 5% for derived values.
- Do not use the "reason" field (too verbose).

## Non-goals

- MAPE/RMSE (not suitable for extraction tasks).
- MoverScore (highly correlated with BERTScore, low marginal gain).

## Links

- Experiment directory: `docs/ab_experiment_*/`
