# ADR-001: 三阶段LLM驱动架构

**Date**: 2025-11-17
**Status**: Accepted
**Related**: [[pipeline]]

## Context

需要设计图表合成系统的整体架构。两种主要选择：
1. 规则驱动画图 + LLM讲解
2. 全LLM驱动（每一步都用LLM）

## Decision

采用三阶段LLM驱动架构：
```
Planner LLM → Coder LLM → (未来) Narrator LLM
```

中间层DataSpec作为约束，既保留LLM灵活性，又限制其在"根据spec和数据画图"的范围内。

## Rationale

**选择此方案**:
- 代码生成比模板填充更灵活，能产生多样化图表
- DataSpec约束避免LLM乱拉数据或偏离需求
- 完整trace支持调试和可重现

**放弃的替代方案**:
- 纯规则驱动：多样性受限，难以覆盖28种图表类型的各种变体
- 单LLM端到端：难以约束和调试，容错性差

## Consequences

### 正面
- 可控多样性：DataSpec正交组合 × LLM创意
- 易调试：每层独立，trace完整
- 可扩展：未来可加Narrator层

### 负面/代价
- 延迟较高：多次LLM调用
- 成本较高：Planner用GPT-5，Coder用Claude Sonnet
