# Feature: refactor-programmatic

Decouple `scripts/run_programmatic.py` (2002 lines, 79KB) into a modular structure in `src/capabilities_v2/`.

## Goal

- Split monolithic script into reusable modules.
- Maintain separation from existing `src/capabilities/` (v1 vs v2).
- Slim down entry script to a CLI layer.

## Structure

```
src/capabilities_v2/
├── __init__.py                    # Unified exports
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

| Original Location | New Location | Description |
|--------|--------|------|
| TaskDefinitionV2, TaskResult | models/task_models.py | Data classes |
| QuotaLoaderV2 | task_generation/quota_loader.py | Quota loading |
| TaskGeneratorV2 | task_generation/task_generator.py | Programmatic task generation |
| ManifestManagerV2 | task_generation/manifest_manager.py | Manifest management |
| SimplifiedPipeline | programmatic_pipeline/simplified_pipeline.py | Execution pipeline |
| ProgressManager | programmatic_pipeline/progress_manager.py | Progress tracking |
| TaskExecutorV2 | programmatic_pipeline/task_executor.py | Concurrent executor |

## Scripts Cleanup

Deprecated scripts removed:
- `run_batch_summary.py` - Batch summarization (integrated into TaskExecutorV2)
- `run_batch.py` - Old batch generation (uses Planner LLM)
- `test_data_fetching.py` - Test scripts
- `visualize_summary.py` - Visualization
- `regenerate_summaries.py` - Re-generation

## Non-goals

- Do not move the `production_4000_v2/` directory.
- Do not remove `src/capabilities/` (v1 pipeline retained).

## Learned

- Entry scripts should only contain CLI parsing and command dispatch.
- Inter-module dependencies via relative imports (`from ..models import ...`).
- Keep v1/v2 coexisting for comparison and rollback.
