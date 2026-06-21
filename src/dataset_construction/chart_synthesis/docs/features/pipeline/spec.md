# Feature: Pipeline - Five-Layer Chart Synthesis Pipeline

## Goal

- Achieve end-to-end automatic synthesis from business requirements to charts + summaries.
- Save complete LLM traces for debugging and reproducibility.

## Architecture

```
L1 Planner → L2 DataSpec Compilation → L3 Data Fetching → L4 Coder → L5 Orchestration
   (GPT-5)      (Rules)                  (API)             (Claude)    (Rules)
```

| Layer | Responsibility |
|------|------|
| L1 | Understand requirements, select chart type/theme/language |
| L2 | Compile Planner output into a complete DataSpec |
| L3 | Fetch data from real APIs based on DataSpec |
| L4 | Generate plotting code and execute |
| L5 | Orchestrate output directory, save complete trace |

## Inputs / Outputs

**Inputs**: `PlannerInput(chart_type, language, theme, task)`

**Outputs**:
```
output_dir/
├── artifacts/chart.png, code.py
├── data/raw.csv, llm_payload.json
├── prompts/*_llm_trace.json  # Complete LLM call records
└── metadata.json, dataspec.json
```

## Constraints

- Planner/Coder prompts are forbidden from containing specific business values.
- Data fetching/LLM parsing/code execution are limited to 3 retries each.

## Edge Cases

- Data source unavailable → Switch to alternative (fallback_allowed).
- Chart type does not match data format → Intercepted by L2 compilation layer.

## Non-goals

- Narrator layer (L6 summary generation) is not yet implemented.
- Batch support for frontend libraries (currently primarily matplotlib).

## Learned

- Complete LLM traces are crucial for debugging.
- `style_intent` is more flexible than hardcoded rules.

## Links

- Code: `src/capabilities/pipeline_orchestration/`
- ADR: [[three-stage-llm]]
