# Feature: DataSpec - Six-Dimensional Orthogonal Data Specification

## Goal

- Achieve controllable diversity through orthogonal parameter combinations.
- Constrain LLMs within the scope of "drawing charts based on spec and data."

## Structure

```python
DataSpec = {
    "shape": "TS_1D | TS_ND | CS_1D | CS_ND | MATRIX",
    "what": { "indicator_id", "data_source", "series_code" },
    "where": { "entity_type", "entities" },
    "when": { "range", "frequency" },
    "how": { "transform", "unit" },
    "output": { "language_config", "library_config", "style_intent" }
}
```

| Dimension | Purpose | Example |
|------|------|------|
| shape | Data form | TS_1D (single time series), CS_ND (multi-dimensional cross-section) |
| what | What is measured | commodity.oil.wti |
| where | Which entities | US, CN |
| when | Time range | 5Y, 30D |
| how | Transformation method | yoy_12m, level |
| output | Presentation configuration | zh-CN, matplotlib |

## Inputs / Outputs

**Inputs**: Coarse-grained plan output by the Planner LLM.

**Outputs**: Complete DataSpec JSON.

## Constraints

- Chart type must match data form (see `chart_library_mapping.yaml`).
- Time series with >200 points or >30 days require `llm_payload_policy` configuration.

## llm_payload_policy

```yaml
llm_payload_policy:
  mode: auto
  ts_policy:
    max_points_raw: 200
    max_horizon_raw: 30D
    repr_id: ts_profile_v1
    include_recent_raw: 30D
```

**Intent**: Long time series are not directly provided in full to the LLM. Instead, feature summaries + recent N days of raw values are given.

## Non-goals

- Implementation details of specific dimensionality reduction algorithms (ts_profile_v1).

## Links

- Configuration: `config/chart_library_mapping.yaml`
- Feature: [[pipeline]]
