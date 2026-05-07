# Feature: DataSpec - 六维正交数据规格

## Goal

- 通过正交参数组合实现可控多样性
- 约束LLM在"根据spec和数据来画图"的范围内

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

| 维度 | 作用 | 示例 |
|------|------|------|
| shape | 数据形态 | TS_1D(单序列), CS_ND(多维横截面) |
| what | 量什么 | commodity.oil.wti |
| where | 哪些实体 | US, CN |
| when | 时间范围 | 5Y, 30D |
| how | 变换方式 | yoy_12m, level |
| output | 呈现配置 | zh-CN, matplotlib |

## Inputs / Outputs

**Inputs**: Planner LLM输出的粗粒度规划

**Outputs**: 完整DataSpec JSON

## Constraints

- 图表类型必须匹配数据形态（见`chart_library_mapping.yaml`）
- 时间序列>200点或>30天需配置`llm_payload_policy`

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

**意图**: 长时间序列不直接全量给LLM，而是给特征摘要+最近N天原始值

## Non-goals

- 具体降维算法（ts_profile_v1）的实现细节

## Links

- 配置: `config/chart_library_mapping.yaml`
- Feature: [[pipeline]]
