# 文档索引

## 阶段说明
- [SFT 阶段](../src/training/sft/CLAUDE.md)
- [DPO 阶段](../src/training/dpo/CLAUDE.md)
- [FCPO 阶段](../src/training/fcpo/docs/CLAUDE.md)
- [评估方法](../src/evaluation/EVALUATION.md)
- [推理参数](../src/inference/INFERENCE_PARAMS.md)

## FCPO 专项文档
| 文档 | 内容 |
|------|------|
| [00-FCPO实验复盘](../src/training/fcpo/docs/00-FCPO实验复盘.md) | 全过程复盘、关键决策与最终方案 |
| [01-实验计划](../src/training/fcpo/docs/01-实验计划.md) | 实验设计与对照组 |
| [02-服务器资源](../src/training/fcpo/docs/02-服务器资源.md) | H20 服务器、Docker、显存分配 |
| [03-API配置](../src/training/fcpo/docs/03-API配置.md) | 评估 / 标注用 API key 与端点 |
| [04-数据构建Pipeline](../src/training/fcpo/docs/04-数据构建Pipeline.md) | 候选生成 → Fact 评分 → 偏好对构建 |
| [05-Fact评分Pipeline对比](../src/training/fcpo/docs/05-Fact评分Pipeline对比.md) | FactScore v1/v2/v3 对比与选型 |
| [06-训练配置教训](../src/training/fcpo/docs/06-训练配置教训.md) | 学习率 / batch / 梯度累计 / OOM 经验 |
| [07-实验方案](../src/training/fcpo/docs/07-实验方案.md) | 最终训练超参与命令 |

## 数据说明
- [SFT 数据](../src/training/sft/data/) — 直接见 `dataset_info.json`
- [DPO 数据](../src/training/dpo/data/README.md) — 仓内文件清单 + GPU 大文件路径
- [FCPO 数据](../src/training/fcpo/data/README.md) — 同上
- [Benchmark 样例](../data/README.md) — 50 条 FinChartSum 样例

## 数据集构建
- [合成图表 README](../src/dataset_construction/chart_synthesis/README.md)
- [合成图表 CLAUDE.md](../src/dataset_construction/chart_synthesis/CLAUDE.md)
- [A/B 实验 README](../src/dataset_construction/ab_experiment/README.md)
- [FinChart 标注系统 README](../src/dataset_construction/annotation/finchart/README.md)
- [FinMME 标注系统 README](../src/dataset_construction/annotation/finmme/README.md)
