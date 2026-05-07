# Feature: refactor-programmatic

将 `scripts/run_programmatic.py` (2002行 79KB) 解耦到 `src/capabilities_v2/` 模块化结构。

## Goal

- 将单体脚本拆分为可复用的模块
- 保持与现有 `src/capabilities/` 的分离（v1 vs v2）
- 入口脚本瘦身为 CLI 层

## Structure

```
src/capabilities_v2/
├── __init__.py                    # 统一导出
├── models/
│   ├── __init__.py
│   └── task_models.py             # TaskDefinitionV2, TaskResult
├── task_generation/
│   ├── __init__.py
│   ├── quota_loader.py            # QuotaLoaderV2
│   ├── task_generator.py          # TaskGeneratorV2
│   └── manifest_manager.py        # ManifestManagerV2
└── programmatic_pipeline/
    ├── __init__.py
    ├── progress_manager.py        # ProgressManager
    ├── simplified_pipeline.py     # SimplifiedPipeline
    └── task_executor.py           # TaskExecutorV2
```

## Changes

| 原位置 | 新位置 | 说明 |
|--------|--------|------|
| TaskDefinitionV2, TaskResult | models/task_models.py | 数据类 |
| QuotaLoaderV2 | task_generation/quota_loader.py | 配额加载 |
| TaskGeneratorV2 | task_generation/task_generator.py | 程序化任务生成 |
| ManifestManagerV2 | task_generation/manifest_manager.py | 清单管理 |
| SimplifiedPipeline | programmatic_pipeline/simplified_pipeline.py | 执行流水线 |
| ProgressManager | programmatic_pipeline/progress_manager.py | 进度跟踪 |
| TaskExecutorV2 | programmatic_pipeline/task_executor.py | 并发执行器 |

## Scripts Cleanup

已删除的废弃脚本：
- `run_batch_summary.py` - 批量总结（已集成到 TaskExecutorV2）
- `run_batch.py` - 旧批量生成（使用 Planner LLM）
- `test_data_fetching.py` - 测试脚本
- `visualize_summary.py` - 可视化
- `补生成_summaries.py` - 补生成

## Non-goals

- 不移动 `production_4000_v2/` 目录
- 不删除 `src/capabilities/`（v1 pipeline 保留）

## Learned

- 入口脚本应仅包含 CLI 解析和命令分发
- 模块间依赖通过相对导入 (`from ..models import ...`)
- 保持 v1/v2 并行存在，便于对比和回退
