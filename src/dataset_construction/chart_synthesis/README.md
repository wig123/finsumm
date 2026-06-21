# Chart Synthesis Pipeline V3

Automated Financial Chart Synthesis System based on Dual-LLM Collaboration - A Complete Pipeline from Business Requirements to Python Code Charts

## 🎯 Core Features

- **Five-layer Pipeline**: Planner (GPT-5) → DataSpec Compilation → Data Acquisition → Coder (Claude 4.5) → Orchestration
- **28 Chart Types**: line, bar, scatter, candlestick, bollinger_bands, etc. (Tier 1-4)
- **10 Financial Themes**: macro_policy, inflation, commodities, equity_markets, etc.
- **4 Visualization Tasks**: monitor, compare, explain, diagnose
- **Real Data Sources**: FRED (13 APIs), AKShare (11 APIs), National Bureau of Statistics, IMF, World Bank, FAO
- **Batch Concurrent Generation**: Supports ThreadPool/ProcessPool, up to 4x acceleration
- **Fully Reproducible**: Saves complete LLM trace (prompt/response/tokens)

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure LLM (API configured easily)
Configuration File: `config/llm_config.yaml`
- Planner: GPT-5 (Business Planning)
- Coder: Claude Sonnet 4.5 (Code Generation)

### 3. Generate a Single Chart
```bash
# Use batch configuration
python scripts/run_batch.py --config batch_configs/demo.yaml

# Or use Python API
python examples/simple_example.py
```

### 4. Batch Generation
```bash
# Quick demo (5 charts, ~2-3 minutes)
python scripts/run_batch.py --config batch_configs/demo.yaml

# Multi-theme balanced (20 charts, ~8-12 minutes)
python scripts/run_batch.py --config batch_configs/multi_theme_balanced.yaml

# Cross-sectional data (7 charts, province/country comparison)
python scripts/run_batch.py --config batch_configs/cross_sectional_demo.yaml
```

## 📁 Project Structure

```
chart-synthesis-v3/
├── config/                      # Configuration files
│   ├── llm_config.yaml         # LLM API configuration
│   ├── theme_mapping.yaml      # 10 financial themes
│   ├── task_mapping.yaml       # 4 visualization tasks
│   ├── chart_library_mapping.yaml  # 28 chart types
│   └── data_source_mapping.yaml    # Data source mapping
├── src/
│   ├── capabilities/           # 5-layer capability implementation
│   │   ├── chart_planning/          # Layer 1: Planner LLM
│   │   ├── dataspec_compilation/    # Layer 2: DataSpec compilation
│   │   ├── data_fetching/           # Layer 3: Data acquisition
│   │   ├── chart_rendering/         # Layer 4: Coder LLM
│   │   └── pipeline_orchestration/  # Layer 5: Orchestration
│   ├── models/                 # Data models (Pydantic)
│   └── utils/                  # Utility functions
├── batch_configs/              # Predefined batch configurations
├── scripts/                    # Batch execution scripts
├── examples/                   # Example code
└── batch_output/               # Batch generation output
```

## 📊 Output Directory Structure

Each generated chart is saved independently:

```
batch_output/demo/20251119_103746_candlestick_en-US_commodities_xxx/
├── artifacts/
│   ├── chart.png               # Generated chart
│   └── code.py                 # Generated Python code
├── data/
│   ├── raw.csv                 # Raw data (CSV)
│   └── llm_payload.json        # Data strategy for LLM
├── prompts/
│   ├── planner_input.json      # Planner input
│   ├── planner_output.json     # Planner output
│   ├── planner_llm_trace.json  # ✅ Complete LLM call record (with prompt/response/tokens)
│   ├── coder_input.json        # Coder input
│   ├── coder_output.json       # Coder output
│   └── coder_llm_trace.json    # ✅ Complete LLM call record
├── logs/
│   └── retry_history.json      # Retry history
├── dataspec.json               # Complete DataSpec
└── metadata.json               # Metadata (status/time/token usage)
```

## 🔧 Python API Usage

```python
from src.models.planner_models import PlannerInput
from src.capabilities.pipeline_orchestration import ChartSynthesisPipeline

# Create input
planner_input = PlannerInput(
    chart_type="candlestick",   # One of 28 chart types
    language="zh-CN",            # zh-CN / en-US
    theme="commodities",         # One of 10 financial themes
    task="monitor"               # One of 4 visualization tasks
)

# Run Pipeline
pipeline = ChartSynthesisPipeline()
result = pipeline.run(planner_input)

print(f"Chart ID: {result['chart_id']}")
print(f"Output Directory: {result['output_dir']}")
print(f"Status: {result['status']}")
```

### Available Themes

| Code | Label | Priority Metric Examples |
|------|------|--------------|
| `macro_policy` | Macro Policy | fed.funds.rate, gdp.real |
| `inflation` | Inflation & Prices | cpi.headline, pce.core |
| `growth_employment` | Growth & Employment | gdp.real, unemployment.rate |
| `commodities` | Commodities | oil.wti, gas.price |
| `equity_markets` | Equity Markets | stock indices |
| `fixed_income` | Fixed Income | 10y.treasury |
| `fx_trade` | FX & Trade | exchange rates |
| `banking_credit` | Banking & Credit | credit growth |
| `corporate_finance` | Corporate Finance | earnings, cash flow |
| `real_estate` | Real Estate | house.price.index |

See `config/theme_mapping.yaml` for details.

### Available Tasks

| Code | Label | Description | Typical Data Form |
|------|------|------|--------------|
| `monitor` | Monitor | Track trends, turning points, latest status | TS_1D |
| `compare` | Compare | Compare different entities/periods/metrics | CS_1D, TS_ND |
| `explain` | Explain | Narrate data stories, event impacts | TS_1D |
| `diagnose` | Diagnose | Identify anomalies, attribution analysis | TS_ND, CS_ND |

See `config/task_mapping.yaml` for details.

## 📈 Batch Configuration Files

Located in the `batch_configs/` directory:

- **demo.yaml**: Quick demo (5 charts, ~2-3 minutes)
- **inflation_analysis.yaml**: In-depth inflation theme analysis (8 charts)
- **cross_sectional_demo.yaml**: Cross-sectional data example (7 charts)
- **multi_theme_balanced.yaml**: Multi-theme balanced distribution (20 charts)

### Configuration File Format

```yaml
batch_name: "demo"
output_base_dir: "./batch_output"

execution:
  parallel: true            # Enable parallel execution
  max_workers: 4            # Concurrency level
  use_process_pool: false   # Thread pool vs process pool

charts:
  - chart_type: line
    language: zh-CN
    theme: inflation
    task: monitor
```

## 🔄 Retry Mechanism

- **LLM Parsing Failure**: Up to 3 retries, with error message
- **Code Execution Failure**: Up to 3 retries, with error stack
- **Data Acquisition Failure**: Up to 3 retries

## 📖 Core Concepts

### DataSpec Six-Dimensional Orthogonal Structure

```python
dataspec = DataSpec(
    shape="TS_1D",              # Data shape: TS_1D, CS_1D, TS_ND, CS_ND
    what={                       # Indicator definition
        "indicator_id": "commodity.oil.wti",
        "data_source": "FRED",
        "series_code": "DCOILWTICO"
    },
    where={                      # Entity scope
        "entity_type": "country",
        "entities": ["US"]
    },
    when={                       # Time dimension
        "range": {"type": "relative", "lookback": "5Y"},
        "frequency": "W"
    },
    how={                        # Data transformation
        "transform": ["level"],
        "unit": "value"
    },
    language_config={...},       # Language configuration
    library_config={...},        # Plotting library configuration
    output={                     # Output configuration
        "style_intent": "..."   # Style intent description
    }
)
```

### Flexible Plotting Mode (v0.3.0)

- **Core Idea**: Describe visualization intent in detail via `style_intent`, with Coder autonomously deciding the specific implementation.
- **Advantages**: Avoids over-annotation, intelligently selects visualization elements based on data characteristics.
- **Example**:
  ```
  "style_intent": "Professional commodities research narrative.
  Highlight major turning points with concise annotations tied to
  known market events. Show immediate market reaction by emphasizing
  price action in the 4–8 weeks after each annotated event..."
  ```

## ⚙️ Configuration Details

### LLM Configuration
```yaml
# config/llm_config.yaml
pipeline_models:
  planner:
    provider: "apiyi"
    model: "gpt-5"              # Business planning
    temperature: 0.7
    max_tokens: 8000

  coder:
    provider: "apiyi"
    model: "claude-sonnet-4-5-20250929"  # Code generation
    temperature: 0.3
    max_tokens: 4000
```

### Data Sources
- **FRED**: 13 U.S. economic time-series indicators
- **AKShare**: 11 Chinese market data APIs
- **National Bureau of Statistics**: Provincial GDP, Provincial Population (Cross-sectional)
- **IMF**: Global Inflation Rate, GDP Growth Rate (Cross-sectional)
- **World Bank**: Global GDP, Global Population (Cross-sectional)
- **FAO**: China Crop Production (Cross-sectional)

## 📝 Version History

### v0.3.0 (2025-11-18) - Current Version
**Flexible Plotting Mode + Full Reproducibility**
- ✅ Removed mandatory annotation constraints, switched to autonomous model decision-making mode
- ✅ Enhanced `style_intent` as the core bridge for conveying visualization intent
- ✅ Planner/Coder prompt optimization, added design principles and evaluation criteria
- ✅ Added complete LLM trace recording: `planner_llm_trace.json`, `coder_llm_trace.json`
  - Includes full prompt, response, token usage
  - Supports fully reproducible debugging and analysis

### v0.2.0 (2025-11-17)
**Cross-sectional Data + Batch Concurrency**
- ✅ Cross-sectional data source support (National Bureau of Statistics, IMF, World Bank, FAO)
- ✅ Batch concurrent generation (ThreadPool/ProcessPool, up to 4x acceleration)
- ✅ Strategic batch generation (balanced, tier-based, cross_sectional_only)

### v0.1.0 (2025-01-17)
**Initial Version**
- ✅ Five-layer Pipeline architecture
- ✅ Dual-LLM collaboration (GPT-5 + Claude 4.5)
- ✅ Time-series data sources (FRED 13 APIs, AKShare 11 APIs)
- ✅ 28 chart type mappings
- ✅ Three-level retry mechanism

## 🐛 Known Limitations

1. **Charting Libraries**: Currently primarily supports matplotlib and mplfinance
2. **Narrator**: Layer 5 summary generation layer is not yet implemented
3. **Data Sources**: All API calls are real requests; network anomalies may cause failures

## 📞 Contact

- Project Repository: [GitHub](https://github.com/your-repo)
- Issue Feedback: GitHub Issues
- License: MIT

---

**Creation Date**: 2025-01-17
**Last Updated**: 2025-11-19
**Current Version**: v0.3.0
