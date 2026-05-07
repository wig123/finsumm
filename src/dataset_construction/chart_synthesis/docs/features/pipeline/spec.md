# Feature: Pipeline - 五层图表合成流水线

## Goal

- 实现从业务需求到图表+总结的端到端自动合成
- 保存完整LLM trace用于调试和可重现性

## Architecture

```
L1 Planner → L2 DataSpec编译 → L3 数据获取 → L4 Coder → L5 编排
   (GPT-5)      (规则)           (API)      (Claude)    (规则)
```

| 层级 | 职责 |
|------|------|
| L1 | 理解需求，选择图表类型/主题/语言 |
| L2 | 将Planner输出编译为完整DataSpec |
| L3 | 根据DataSpec从真实API拉取数据 |
| L4 | 生成绘图代码并执行 |
| L5 | 编排输出目录，保存完整trace |

## Inputs / Outputs

**Inputs**: `PlannerInput(chart_type, language, theme, task)`

**Outputs**:
```
output_dir/
├── artifacts/chart.png, code.py
├── data/raw.csv, llm_payload.json
├── prompts/*_llm_trace.json  # 完整LLM调用记录
└── metadata.json, dataspec.json
```

## Constraints

- Planner/Coder提示词禁止具体业务值
- 数据获取/LLM解析/代码执行各3次重试

## Edge Cases

- 数据源不可用 → 切换备选（fallback_allowed）
- 图表类型与数据形态不匹配 → L2编译层拦截

## Non-goals

- Narrator层（L6总结生成）暂未实现
- 前端库批量支持（当前主要matplotlib）

## Learned

- 完整LLM trace对调试至关重要
- style_intent比硬编码规则更灵活

## Links

- 代码: `src/capabilities/pipeline_orchestration/`
- ADR: [[three-stage-llm]]
