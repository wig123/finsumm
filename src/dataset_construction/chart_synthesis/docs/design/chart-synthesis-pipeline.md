# Financial Chart Synthesis Pipeline

## Overview

An end-to-end pipeline for generating financial chart data, from business requirements to final charts and summaries.

**Core Features**:
- Input-driven control over chart types and language distribution.
- Utilizes real financial data sources (FRED/AKShare).
- LLM-driven code generation and summary writing.
- Supports 28 chart types with bilingual output (Chinese/English).

---

## Pipeline Architecture

```
[External Control Layer] Generate sampling plan
    ↓ {chart_type, language, theme, role, task}

[Layer 1] Planner LLM - Business planning
    ↓ question + data_requirement + labels

[Layer 2] DataSpec compilation - Normalization
    ↓ Complete DataSpec (six orthogonal dimensions)

[Layer 3] Data preparation - Real data
    ↓ DataFrame + LLM Payload

[Layer 4] Coder LLM - Code generation
    ↓ Python/JS code + image

[Layer 5] Narrator LLM - Summary generation
    ↓ Natural language description
```

---

## Core Concepts

### 1. DataSpec (Six Orthogonal Dimensions)

A standardized description of data requirements, encompassing six orthogonal dimensions:

| Dimension | Description | Example |
|-----------|-------------|---------|
| **Shape** | Data form | `TS_1D` (univariate time series), `CS_1D` (univariate cross-section) |
| **What** | Measurement object | Metric (CPI YoY), Data source (FRED), Series code |
| **Where** | Measurement scope | Entity type (Country), Entity list ([US, CN]) |
| **When** | Time dimension | Time range (last 20 years), Frequency (monthly) |
| **How** | Data transformation | Transformation method (YoY), Adjustment (seasonally adjusted) |
| **LLM_Payload** | Data strategy for LLM | Dimensionality reduction for long time series, retain original for short time series/cross-section |

**Further Reading**: Detailed DataSpec specification can be found in `dataspec-specification.md` (to be created).

---

### 2. Chart Type Distribution

Hierarchical distribution based on frequency of use in real financial scenarios:

- **Tier 1 (60%)**: Core types - line, candlestick, bar, area, histogram, scatter
- **Tier 2 (25%)**: High-frequency analysis - heatmap, waterfall, OHLC, Bollinger Bands, box, pie
- **Tier 3 (10%)**: Professional tools - contour, Fan Chart, Volume Profile, Ichimoku Cloud
- **Tier 4 (5%)**: Special scenarios - node, Gantt, Point & Figure

**Reference Document**: `chart-distribution-strategy.md`

---

### 3. Chart Type to Plotting Library Mapping

Predefined optimal plotting libraries for each chart type:

| Chart Type | Python Library | Frontend Library | Tier |
|------------|----------------|------------------|------|
| line | matplotlib | ECharts | 1 |
| candlestick | mplfinance | Highstock | 1 |
| heatmap | seaborn | ECharts | 2 |
| waterfall | plotly | Highcharts | 2 |

**Reference Document**: `chart-library-mapping.md`

---

### 4. Data Sources

7 real data sources, covering time series and cross-sectional data:

**Time Series Data**:
- **FRED** (13 series): US Macro/Commodity/Energy Data
- **AKShare** (11 interfaces): China Agricultural/Energy/Macro Data

**Cross-Sectional Data**:
- National Bureau of Statistics, IMF, UN Comtrade, FAOSTAT, World Bank

**Reference Document**: `../test/data_sources_test/README.md`

---

## Key Processes

### External Control Layer → Planner Input

**Directly Specified at Input**:
```json
{
  "chart_type": "line",        // Specify from 28 types
  "language": "zh-CN",         // zh-CN | en-US
  "theme": "macro",            // 8 major themes
  "role": "macro_strategist",  // 7 roles
  "task": "trend"              // 8 task types
}
```

**Handled by External Control Layer**:
- Sample chart types by `chart-distribution-strategy.md` weights.
- Sample languages proportionally (recommend 60% zh-CN, 40% en-US).
- Combine Theme × Role × Task (consider compatibility).

---

### Planner LLM → Business Planning

**Responsibility**: Generate business logic based on specified configurations.

**Output**:
```json
{
  "question": "What is the US inflation trend over the past 20 years?",
  "data_requirement": {
    "indicator": "macro.inflation.cpi.headline",
    "entities": ["US"],
    "time_horizon": "20Y",
    "frequency": "M",
    "data_source": "FRED"
  },
  "labels": {
    "title": "US CPI Year-over-Year Trend (2005-2025)",
    "x_label": "Date",
    "y_label": "YoY Growth Rate (%)"
  },
  "style_intent": "Macro research report style, annotate key points",
  "annotations": ["last_value", "max", "min"]
}
```

**Not Responsible For**: Selecting chart types or languages (specified at input).

---

### DataSpec Compilation → Normalization

**Responsibility**: Convert Planner output into a complete DataSpec.

**Core Operations**:
1. Query `chart-library-mapping` table: `chart_type → {python_lib, frontend_lib}`
2. Configure font settings based on `language`.
3. Map data sources: `indicator → FRED/AKShare series_code`
4. Infer data shape: `Shape` (TS_1D/CS_1D/...)
5. Construct `llm_payload_policy`: Dimensionality reduction for long time series, retain original for short time series.

---

### Data Preparation → Real Data

**Responsibility**: Fetch data from sources and apply strategies.

**Processing Logic**:
```python
if shape == "TS_1D" and (num_points > 200 or time_span > 30_days):
    to_LLM: {
        "repr": time_series_statistical_features (extrema/inflection_points/intervals),
        "recent_raw": last_30_days_raw_data
    }
else:
    to_LLM: full_raw_data
```

---

### Coder LLM → Code Generation

**Responsibility**: Generate plotting code for specified libraries and languages.

**Input**:
- DataFrame (real data)
- DataSpec (including library and language configurations)

**Output**:
- Executable Python/JS code
- Generated images (with specified language labels)

**Language Handling**:
- `zh-CN`: Configure Chinese fonts (`Arial Unicode MS`, `SimHei`).
- `en-US`: Use default English fonts.

---

### Narrator LLM → Summary Generation

**Responsibility**: Write chart summaries in the specified language.

**Input**:
- Image
- DataSpec metadata
- Key numerical points (to avoid LLM hallucinations)
- (Optional) Generated code

**Constraints**:
- All numbers must reference provided key points.
- Write in the specified language.
- Adhere to professional expression style consistent with the role.

---

## LLM Data Exposure Strategy

### Time Series Data vs. Cross-Sectional Data

| Data Type | Condition | Strategy for LLM |
|-----------|-----------|------------------|
| **Long Time Series** | Points > 200 or Span > 30 days | Dimensionality reduction representation + last 30 days original data |
| **Short Time Series** | Points ≤ 200 AND Span ≤ 30 days | Full original data |
| **Cross-Sectional** | Shape = CS_* | Full original data (rows < 500) |

**Motivation**:
- Providing full long time series to LLM can lead to errors (e.g., daily stock data for a year).
- Balancing accuracy with statistical features from dimensionality reduction and partial original data.

**Dimensionality Reduction Methods** (Optional):
- Simple statistical features (min/max/mean/inflection points)
- TSFresh time series feature extraction
- TS2Vec deep learning representation

---

## Tech Stack

### Data Sources
- FRED: `pandas-datareader`
- AKShare: `akshare`
- Cross-Sectional: Direct HTTP requests

### Plotting Libraries
- **Tier 1 Core**: `matplotlib`, `mplfinance`
- **Tier 2 High-Frequency**: `seaborn`, `plotly`
- **Tier 3-4**: `matplotlib`, `mplfinance`, `plotly`, `networkx`

**Reference Document**: `library-installation.md`

### LLM Calls
- Provider: OpenRouter/OpenAI/Anthropic
- Integrated Clients: `src/chart_synth_v2/services/llm/`

---

## Output Structure

Each generated chart includes:

```
output/20251117_143052_line_zh-CN_macro_a3f8b2d1/
├── chart.png              # Generated image
├── code.py                # Plotting code
├── summary.txt            # Natural language summary
├── dataspec.json          # Complete DataSpec
├── data.csv               # Real data used
└── metadata.json          # Metadata (timestamp/status/configuration)
```

---

## Further Reading

- `chart-distribution-strategy.md` - Hierarchical distribution of 28 chart types.
- `chart-library-mapping.md` - Chart type to plotting library mapping table.
- `library-installation.md` - Python plotting library installation guide.
- `../test/data_sources_test/README.md` - Detailed data source descriptions.
- `../src/chart_synth_v2/models/enums.py` - Theme/Role/Task enumeration definitions.

---

**Creation Date**: 2025-01-17
**Maintainers**: Chart Synthesis Project Team

---
