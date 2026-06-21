# ADR-001: Three-Stage LLM-Driven Architecture

**Date**: 2025-11-17
**Status**: Accepted
**Related**: [[pipeline]]

## Context

The overall architecture for the chart synthesis system needs to be designed. Two main options:
1. Rule-driven chart generation + LLM explanation
2. Fully LLM-driven (LLM used in every step)

## Decision

Adopt a three-stage LLM-driven architecture:
```
Planner LLM → Coder LLM → (Future) Narrator LLM
```

The intermediate DataSpec layer acts as a constraint, both preserving LLM flexibility and limiting it to the scope of "generating charts based on spec and data."

## Rationale

**Chosen Solution**:
- Code generation is more flexible than template filling, capable of producing diverse charts.
- DataSpec constraints prevent the LLM from arbitrarily fetching data or deviating from requirements.
- Complete trace supports debugging and reproducibility.

**Rejected Alternatives**:
- Pure rule-driven: Limited diversity, difficult to cover various variants of 28 chart types.
- Single LLM end-to-end: Difficult to constrain and debug, poor fault tolerance.

## Consequences

### Positive
- Controlled diversity: Orthogonal combination of DataSpec × LLM creativity.
- Easy to debug: Each layer is independent, with a complete trace.
- Extensible: A Narrator layer can be added in the future.

### Negative / Costs
- Higher latency: Multiple LLM calls.
- Higher cost: Planner uses GPT-5, Coder uses Claude Sonnet.
