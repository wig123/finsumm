# Chart Synthesis V3

A programmatic synthesis system for financial chart-summary pairs, designed to fine-tune the chart understanding capabilities of multimodal large models.

## Goals & Non-goals

**Goals**:
- Generate high-quality financial chart-summary pair training data
- Reduce summary error rate by leveraging code and data context
- Support 28 chart types, 10 financial themes, and bilingual (Chinese & English)

**Non-goals**:
- Not a real-time data display system
- Not a general-purpose visualization tool (focused on the financial domain)

## Tech Stack

- **LLM**: GPT-5 (Planner) + Claude Sonnet 4.5 (Coder)
- **Plotting**: matplotlib, mplfinance, plotly, ECharts, Highcharts
- **Data Sources**: FRED, AKShare, National Bureau of Statistics of China, IMF, World Bank

## Directory Map

```
chart-synthesis-v3/
├── docs/                 # Documentation system
│   ├── _ai-rules.md      # AI writing rules (required reading)
│   ├── decisions/        # ADR
│   └── features/         # Feature documentation
├── config/               # Configuration (LLM/themes/chart types/data sources)
├── prompts/              # LLM prompt templates
├── src/capabilities/     # Five-layer Pipeline implementation
│   ├── chart_planning/        # L1: Planner
│   ├── dataspec_compilation/  # L2: DataSpec compilation
│   ├── data_fetching/         # L3: Data fetching
│   ├── chart_rendering/       # L4: Coder
│   └── pipeline_orchestration/# L5: Orchestration
├── batch_configs/        # Batch generation configuration
├── scripts/              # Run scripts
└── production_*/         # Production datasets
```

## Architecture

**5-Layer Pipeline**:
```
Planner LLM → DataSpec compilation → Data fetching → Coder LLM → Orchestration output
```

**Core Design Principles**:
- DataSpec 6-Dimensional Orthogonality: shape × what × where × when × how × output
- Time Series Dimensionality Reduction: Trigger feature extraction for >200 points or >30 days
- Authentic Financial Style: Minimalist labeling, no decorative elements

## Commands

```bash
# Single chart generation
python scripts/run_batch.py --config batch_configs/demo.yaml

# Batch generation (with progress monitoring)
python scripts/run_batch.py --config batch_configs/production_1000.yaml &
./monitor_progress.sh
```

## Rules for Claude

1. **Before writing documentation**: Must first read `docs/_ai-rules.md`
2. **For new features**: **Must** use `./docs/_scripts/new.sh feat <name>`
3. **Prompt modifications**:
   - Rules can be tailored to chart types
   - **Do not** use specific business values (e.g., CPI=3.2%) as examples
4. **Chart Style**:
   - Default to minimalist, prohibit decorative annotations
   - Reference Bloomberg/FRED style, not for instructional demonstrations
5. **If unsure**: First analyze (`--analyze-only`), then execute after confirmation

## Task State

- `docs/features/<name>/spec.md` - Feature Specification (Stable)
- `docs/features/<name>/state.md` - Progress Tracking (Delete after completion)

Major decisions are synchronized to `docs/decisions/*.adr.md`
