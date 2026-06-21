# Batch Configuration Files Guide

This directory contains predefined batch generation configuration files for demonstration and quick start.

## Configuration File List

### 1. `demo.yaml` - Quick Demo
- **Purpose**: Small-scale testing, verify system functionality
- **Number of Charts**: 5
- **Features**: Covers basic chart types and themes, suitable for first-time runs
- **Execution Time**: ~2-3 minutes (concurrent)

```bash
# Preview
python scripts/run_batch.py --config batch_configs/demo.yaml --dry-run

# Execute
python scripts/run_batch.py --config batch_configs/demo.yaml
```

### 2. `inflation_analysis.yaml` - Inflation Theme Deep Dive
- **Purpose**: Multi-dimensional visualization of a single theme
- **Number of Charts**: 8
- **Features**: Covers 4 types of visualization tasks (monitor/compare/explain/diagnose)
- **Execution Time**: ~3-5 minutes (concurrent)

```bash
python scripts/run_batch.py --config batch_configs/inflation_analysis.yaml
```

### 3. `cross_sectional_demo.yaml` - Cross-sectional Data Example
- **Purpose**: Demonstrates cross-entity comparative analysis (provinces, countries)
- **Number of Charts**: 7
- **Features**: Uses real cross-sectional data sources (National Bureau of Statistics, IMF, World Bank, FAO)
- **Execution Time**: ~3-4 minutes (concurrent)

```bash
python scripts/run_batch.py --config batch_configs/cross_sectional_demo.yaml
```

### 4. `multi_theme_balanced.yaml` - Multi-theme Balanced Distribution
- **Purpose**: Large-scale batch generation, covering all major themes
- **Number of Charts**: 20
- **Features**: 10 themes × 2 tasks, balanced distribution
- **Execution Time**: ~8-12 minutes (concurrent)

```bash
python scripts/run_batch.py --config batch_configs/multi_theme_balanced.yaml
```

## Configuration File Structure

```yaml
# Batch name (used for output directory naming)
batch_name: "your_batch_name"

# Output root directory
output_base_dir: "./batch_output"

# Execution configuration
execution:
  parallel: true           # Whether to execute in parallel
  max_workers: 4           # Maximum concurrency (recommended 2-8)
  use_process_pool: false  # Whether to use process pool (default thread pool)

# Chart list
charts:
  - chart_type: line       # Chart type (line/bar/scatter, etc.)
    language: zh-CN        # Language (zh-CN/en-US)
    theme: inflation       # Theme (see theme list below)
    task: monitor          # Task (monitor/compare/explain/diagnose)
    data_constraints: {}   # Data constraints (optional)
```

## Supported Themes (Theme)

1. `macro_policy` - Macro Policy
2. `inflation` - Inflation and Prices
3. `growth_employment` - Growth and Employment
4. `fx_trade` - Foreign Exchange and Trade
5. `equity_markets` - Equity Markets
6. `fixed_income` - Fixed Income
7. `commodities` - Commodities
8. `banking_credit` - Banking and Credit
9. `corporate_finance` - Corporate Finance
10. `real_estate` - Real Estate

## Supported Tasks (Task)

1. `monitor` - Monitor Trends
2. `compare` - Comparative Analysis
3. `explain` - Explain Relationships
4. `diagnose` - Diagnose Anomalies

## Supported Chart Types

- `line` - Line Chart
- `bar` - Bar Chart
- `scatter` - Scatter Plot
- `area` - Area Chart
- `pie` - Pie Chart
- etc. (refer to `config/chart_library_mapping.yaml`)

## Output Directory Structure

After execution, the following will be generated in the `output_base_dir/batch_name/` directory:

```
batch_output/
└── demo/
    ├── batch_summary.json              # Batch run summary
    ├── line_zh-CN_inflation_20250117_120000/  # Individual chart directory
    │   ├── artifacts/
    │   │   ├── chart.png               # Generated chart
    │   │   └── code.py                 # Generated code
    │   ├── data/
    │   │   ├── raw.csv                 # Raw data
    │   │   └── llm_payload.json        # LLM data strategy
    │   ├── prompts/
    │   │   ├── planner_input.json
    │   │   ├── planner_output.json
    │   │   ├── coder_input.json
    │   │   └── coder_output.json
    │   ├── logs/
    │   │   └── retry_history.json
    │   └── metadata.json               # Chart metadata
    └── ...
```

## Advanced Usage

### Custom Data Constraints

```yaml
charts:
  - chart_type: line
    language: zh-CN
    theme: inflation
    task: monitor
    data_constraints:
      preferred_indicators:
        - macro.inflation.cpi.headline
      time_range_hint: "recent_2y"
```

### Adjust Concurrency Configuration

```yaml
execution:
  parallel: true
  max_workers: 8              # Increase concurrency
  use_process_pool: true      # Use process pool (suitable for CPU-intensive tasks)
```

## FAQ

### Q: How to choose `max_workers`?
A: It is recommended to set based on CPU core count and network bandwidth:
- Local run: 2-4 workers
- High-performance server: 4-8 workers
- Network-limited environments: reduce to 2-3

### Q: Thread Pool vs. Process Pool?
A:
- **Thread Pool** (default): Suitable for I/O-bound tasks (API calls, LLM requests)
- **Process Pool**: Suitable for CPU-bound tasks (large-scale data processing, complex computations)

### Q: How to handle failed charts?
A: Check the `results` array in `batch_summary.json`. Failed items contain error messages. You can extract failed items and regenerate them.

## Example Workflow

```bash
# 1. Preview configuration
python scripts/run_batch.py --config batch_configs/demo.yaml --dry-run

# 2. Review preview output, execute after confirmation
python scripts/run_batch.py --config batch_configs/demo.yaml

# 3. View batch summary
cat batch_output/demo/batch_summary.json | jq .

# 4. View generated charts
ls batch_output/demo/*/artifacts/chart.png
```

## Reference Documentation

- Pipeline Principles: `../docs/chart-synthesis-pipeline.md`
- Project Status: `../PROJECT_STATUS.md`
- Quick Start: `../QUICKSTART.md`
