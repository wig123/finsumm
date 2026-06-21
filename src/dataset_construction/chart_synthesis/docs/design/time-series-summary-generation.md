# Time Series Summarization Method

## Overview

A general-purpose financial time series automatic summarization system. Input: (Date, Value) data. Output: Structured Markdown summary + visualization charts.

**Core Features**:
- Requires only two columns of data, no derived fields like returns/volume.
- 6 analysis dimensions, comprehensively covering trends, extremes, volatility, and risk.
- Adaptive parameters, supporting data ranges from half a year to 10 years.
- LLM-friendly Markdown output format.

---

## Analysis Dimensions

### 1. Global Statistics
Basic statistics: Mean, Standard Deviation, Skewness, Kurtosis, Annualized Volatility.

### 2. Segmented Analysis (pwlf)
- Method: Piecewise linear fitting.
- Parameters: n_segments=12, R²≈0.93.
- Output: 12 linear segments, labeled as uptrend/downtrend/sideways.

### 3. Change Point Detection
- Mutation intensity based on segment boundaries.
- Types: Trend reversal/slope change/minor fluctuation.
- Intensity: 1-5 star rating.

### 4. Extremum Point Detection (scipy_peaks)
- Parameters: prominence=1.0×std, distance=3%.
- Output: Peaks and valleys, sorted by significance.

### 5. Volatility Regime Identification (Adaptive)
- Smoothing window: 3% of data length (min 10 days, max 60 days).
- Minimum regime duration: 2.5% of data length (min 5 days, max 60 days).
- Quantiles: 25%/75% (low/medium/high volatility).

### 6. Risk Metrics
- Maximum Drawdown (time interval + magnitude).
- Longest consecutive drawdown period.

---

## Core Algorithms

### pwlf Piecewise Linear Fitting
```python
# Fit time series into 12 linear segments
my_pwlf = pwlf.PiecewiseLinFit(x, y)
breaks = my_pwlf.fit(12)
slopes = my_pwlf.slopes  # Slope of each segment
```

**Advantages**:
- High goodness-of-fit (R²>0.93).
- Strong interpretability (clear trend for each segment).
- Automatic identification of turning points.

### scipy.signal.find_peaks Extremum Detection
```python
# prominence: Peak significance threshold (1.0×standard deviation)
# distance: Minimum distance between peaks (3% of data)
peaks, props = find_peaks(y, prominence=std, distance=0.03*n)
```

**Advantages**:
- Filters out noise, retaining only significant extrema.
- Automatic sorting, highlighting important peaks and valleys.

### Adaptive Volatility Regime Identification
```python
# Smoothing window = 3% of data length
smooth_window = max(10, min(60, int(n * 0.03)))

# Minimum regime = 2.5% of data length
min_duration = max(5, min(60, int(n * 0.025)))

# Extreme quantiles (identify major regimes)
low_mid = 25th percentile
mid_high = 75th percentile
```

**Adaptive Performance**:
| Data Length | Smoothing Window | Minimum Regime Duration |
|-------------|------------------|-------------------------|
| Half Year (126 days) | 10 days | 5 days |
| 1 Year (252 days) | 10 days | 5 days |
| 5 Years (1260 days) | 36 days | 30 days |
| 10 Years (2520 days) | 60 days | 60 days |

---

## Output Structure

```
output/
├── meta.json                      # Method version and parameters
├── 00_overview.md                 # Overview
├── 01_global_stats.md            # Global statistics
├── 02_segments.md                # Segmented analysis
├── 03_changepoints.md            # Change point detection
├── 04_extrema.md                 # Extremum points
├── 05_volatility.md              # Volatility regimes
├── 06_risk.md                    # Risk metrics
├── visualizations/
│   ├── full_overview.png         # Comprehensive overview
│   ├── segments.png              # Segment fitting
│   ├── changepoints.png          # Change point annotations
│   └── extrema.png               # Peak and valley annotations
└── data/
    └── processed_data.csv        # Processed data
```

---

## Usage Example

```python
from pathlib import Path
import pandas as pd

# Load data (only DATE and VALUE columns required)
df = pd.read_csv('data.csv', parse_dates=['DATE'], index_col='DATE')

# Initialize analyzer
analyzer = TimeSeriesAnalyzer(df, series_name='Stock_A')

# Execute analysis
results = analyzer.analyze_all()

# Generate visualizations
visualizer = Visualizer(df, results, output_dir='output')
visualizer.create_all()

# Generate Markdown summary
md_gen = MarkdownGenerator(results, output_dir='output')
md_gen.generate_all()
```

**Execution Time**: ~100 seconds (1241 data points).

---

## Parameter Configuration

### Core Parameters (Tuned)

| Module | Parameter | Default Value | Description |
|--------|-----------|---------------|-------------|
| pwlf | n_segments | 12 | Number of segments |
| scipy_peaks | prominence | 1.0×std | Peak prominence |
| scipy_peaks | distance | 3% | Minimum peak distance |
| volatility | smooth_pct | 3% | Smoothing window percentage |
| volatility | min_duration_pct | 2.5% | Minimum regime duration percentage |
| volatility | quantiles | 25%/75% | Quantile thresholds |

### When to Adjust

**High-Frequency Data** (minute/hour):
- pwlf: n_segments → 24-48
- volatility: smooth_pct → 1-2%

**Extremely Volatile Markets**:
- scipy_peaks: prominence → 1.5×std
- volatility: quantiles → 20%/80%

---

## Design Philosophy

### 1. Universality First
- Requires only (Date, Value), no domain-specific fields.
- Applicable to all financial time series like stocks, futures, forex, commodities, etc.

### 2. Adaptive Parameters
- Dynamically adjusts windows/thresholds based on data length.
- Avoids fixed parameters failing across different time spans.

### 3. LLM Friendly
- Markdown structured output.
- Tabular presentation for easy LLM parsing.
- Clear navigation links.

### 4. Interpretability
- All metrics have financial meaning.
- Avoids black-box models (e.g., deep learning).
- Facilitates manual verification and debugging.

---

## Application Scenarios

### 1. LLM Training Data Generation
Generate (chart, summary) pairs for training chart understanding models:
```
Input: Time series PNG chart
Output: "The series is divided into 12 segments, segment 3 (2022-02-16 to 2023-01-03) is a high volatility period..."
```

### 2. Automated Reporting
Batch generation of standardized summaries for all assets in an investment portfolio.

### 3. Quick Analysis
Key features of historical price trends for novice investors to quickly understand.

### 4. Data Preprocessing
Provides structured features for downstream tasks (prediction/classification).

---

## Version History

### v2.2 (Current) - 2025-11-17
- ✅ Removed pattern analysis module (low information value).
- ✅ Volatility regime changed to adaptive thresholds.
- ✅ 6 core analysis dimensions.

### v2.1 - 2025-11-17
- ✅ Improved volatility regime identification (reduced number of regimes).
- ⚠️ Used fixed thresholds (corrected in v2.2).

### v2.0 - 2025-11-16
- ✅ Removed anomaly detection module (redundant with extremum detection).

### v1.0 - 2025-11-15
- Initial version, 8 analysis dimensions.

---

## Tech Stack

- **Python** 3.x
- **pwlf** - Piecewise linear fitting
- **scipy** - Signal processing (peak detection)
- **numpy** - Numerical computation
- **pandas** - Data manipulation
- **matplotlib** - Visualization

---

## Code Location

- Main program: `test/ts_summary_research/test_comprehensive_summary_v2.py`
- Test scripts: `test/ts_summary_research/test_adaptive_thresholds.py`
- Full documentation: `test/ts_summary_research/CHANGELOG_v2.2.md`

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Processing Speed | ~100 seconds/1241 points |
| Memory Usage | ~20MB |
| Output Size | ~12MB |
| Accuracy | R²=0.93 (segment fitting) |

---

## Limitations

1. **Univariate Only**: Cannot handle joint analysis of price and volume.
2. **No Causal Inference**: Does not explain the reasons for regime switches.
3. **Static Analysis**: Does not support streaming/incremental updates.
4. **Daily Data Optimization**: High-frequency data requires parameter adjustments.

---

## Citation Format

```
Time Series Comprehensive Summary System v2.2
https://github.com/[your-repo]/ts_summary_research
Method: pwlf segmentation + scipy peak detection + adaptive volatility regime identification
```

---
