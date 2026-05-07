# Feature: Evaluation - 图表总结质量评估

## Goal

- 评估模型生成总结的准确性和完整性
- 区分数值准确、语义相似、数据接地三个维度

## 评估层级

| 层级 | 指标 | 优先级 |
|------|------|--------|
| P0 | Numerical F1 (数值准确) | 必须 |
| P0 | PARENT (数据接地) | 必须 |
| P1 | CIDEr (关键信息覆盖) | 推荐 |
| P1 | Entity F1 (实体准确) | 推荐 |
| P1 | BLEURT (整体质量) | 推荐 |
| P2 | FactScore v2 | 可选 |

## Inputs / Outputs

**Inputs**:
- 模型生成的总结（prediction）
- 参考总结（reference）
- 图表图片（chart.png）

**Outputs**: 评估分数 + 事实级别诊断

## FactScore v2 设计

```
pred_facts → 与 ref_facts 对比
          → 匹配: Ref Match
          → 不匹配: 由GPT-4判断是否图表支持
                  → 支持: Chart Support
                  → 不支持: 错误
```

**关键决策**:
- 数值比对用规则计算（避免模型误差）
- 区分"参考匹配"和"图表支持"两种正确类型

## Constraints

- 数值容差: 精确值1%, 推导值5%
- 不使用reason字段（太长）

## Non-goals

- MAPE/RMSE（不适合提取任务）
- MoverScore（与BERTScore高度相关，边际收益低）

## Links

- 实验目录: `docs/ab_experiment_*/`
