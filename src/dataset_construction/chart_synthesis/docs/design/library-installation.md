# Python Library Installation Guide

## Current Environment Status

**Virtual Environment**: `.venv`
**Python Version**: 3.13.6
**Last Updated**: 2025-01-17

---

## Installed Core Libraries

### Plotting Core (6 libraries)

| Library Name | Version | Purpose |
|--------------|---------|---------|
| **matplotlib** | 3.10.7 | Basic charts (line/bar/area/histogram/scatter/contour/errorbar) |
| **seaborn** | 0.13.2 | Statistical charts (heatmap/box/density) |
| **plotly** | 6.3.1 | Interactive charts (waterfall/treemap/overlay/gantt/depth) |
| **mplfinance** | 0.12.10b0 | Financial charts (candlestick/OHLC/volume/Bollinger/Ichimoku/Renko) |
| **networkx** | 3.5 | Network graph layout |
| **squarify** | 0.4.4 | Treemap layout algorithm |

### Data Processing (3 libraries)

| Library Name | Version | Purpose |
|--------------|---------|---------|
| **pandas** | 2.3.3 | Data manipulation |
| **numpy** | 2.2.6 | Numerical computation |
| **scipy** | 1.16.2 | Scientific computation (contour/density) |

### Technical Indicators (2 libraries)

| Library Name | Version | Purpose |
|--------------|---------|---------|
| **pandas-ta** | 0.4.71b0 | Technical indicator calculation (Bollinger/MACD/RSI, etc.) |
| **statsmodels** | 0.14.5 | Statistical modeling (time series analysis/regression) |

### Export Support (1 library)

| Library Name | Version | Purpose |
|--------------|---------|---------|
| **kaleido** | 1.2.0 | Plotly static image export (PNG/SVG/PDF) |

---

## Installation Commands

### Full Installation (Recommended)
```bash
# Activate virtual environment
source .venv/bin/activate

# Core plotting libraries
pip install matplotlib seaborn plotly mplfinance networkx squarify

# Data processing
pip install pandas numpy scipy

# Technical indicators
pip install pandas-ta statsmodels

# Export support
pip install kaleido
```

### Tiered Installation (On Demand)

**Tier 1: Core Plotting (Tier 1 Essential)**
```bash
pip install matplotlib mplfinance pandas numpy
```

**Tier 2: Statistical Analysis (Tier 2 Essential)**
```bash
pip install seaborn plotly scipy
```

**Tier 3: Technical Indicators (Tier 3 Essential)**
```bash
pip install pandas-ta statsmodels
```

**Tier 4: Advanced Features (Optional)**
```bash
pip install networkx squarify kaleido
```

---

## Chart Type Coverage Matrix

### Tier 1 Core (8 types) ✅ Fully Supported

| Chart Type | Primary Library | Supporting Library |
|------------|-----------------|--------------------|
| line | matplotlib | - |
| candlestick | mplfinance | - |
| bar | matplotlib | - |
| bar + line overlay | plotly | matplotlib |
| candlestick + volume | mplfinance | - |
| area | matplotlib | - |
| histogram | matplotlib | - |
| scatter | matplotlib | - |

### Tier 2 High Frequency (9 types) ✅ Fully Supported

| Chart Type | Primary Library | Supporting Library |
|------------|-----------------|--------------------|
| heatmap | seaborn | matplotlib |
| waterfall | plotly | - |
| OHLC | mplfinance | - |
| Bollinger Bands | mplfinance | pandas-ta |
| box | seaborn | matplotlib |
| pie | matplotlib | - |
| bubble | matplotlib | - |
| line + band overlay | matplotlib | - |
| treemap | plotly | squarify |

### Tier 3 Professional (8 types) ✅ Fully Supported

| Chart Type | Primary Library | Supporting Library |
|------------|-----------------|--------------------|
| contour | matplotlib | scipy |
| Fan Chart | matplotlib | - |
| Volume Profile | matplotlib | pandas |
| Ichimoku Cloud | mplfinance | pandas-ta |
| Market Depth | plotly | - |
| Renko | mplfinance | - |
| errorbar | matplotlib | - |
| radar | plotly | - |

### Tier 4 Special (7 types) ✅ Fully Supported

| Chart Type | Primary Library | Supporting Library |
|------------|-----------------|--------------------|
| node | networkx | matplotlib |
| Gantt | plotly | - |
| Point & Figure | mplfinance | - |
| candlestick + indicator | mplfinance | pandas-ta |
| waterfall + line | plotly | - |
| density | seaborn | scipy |
| heatmap + scatter | seaborn | matplotlib |

**Total**: 28 Chart Types 100% Coverage ✅

---

## Verify Installation

```python
# Run this script to verify all libraries are available
import matplotlib
import seaborn
import plotly
import mplfinance
import networkx
import pandas
import numpy
import scipy
import statsmodels
import squarify
import kaleido

print("✅ All core libraries installed successfully!")
print(f"matplotlib: {matplotlib.__version__}")
print(f"mplfinance: {mplfinance.__version__}")
print(f"plotly: {plotly.__version__}")
print(f"seaborn: {seaborn.__version__}")
print(f"pandas-ta: {import pandas_ta; pandas_ta.__version__}")
```

---

## Library Version Compatibility

| Python Version | Recommended Library Version | Notes |
|----------------|-----------------------------|-------|
| 3.13.x | Current Version | ✅ Verified |
| 3.12.x | Current Version | ✅ Compatible |
| 3.11.x | matplotlib>=3.8 | ⚠️ mplfinance downgrade required |
| 3.10.x | matplotlib>=3.7 | ⚠️ Dependency adjustment needed |

---

## Frequently Asked Questions

### Q1: mplfinance version shows beta?
**A**: `0.12.10b0` is a stable beta version with full functionality. Recommended for financial charts.

### Q2: kaleido installation failed?
**A**: Primarily used for Plotly static export, not essential. Can be skipped or replaced with `orca`.

### Q3: pandas-ta installation failed?
**A**: TA-Lib can be used as an alternative, but pandas-ta is easier to install (pure Python implementation).

### Q4: How to reduce environment size?
**A**:
- Tier 1 Only: ~200MB (matplotlib + mplfinance)
- Tier 1-2: ~350MB (+ seaborn + plotly)
- Full Installation: ~500MB

---

## Export requirements.txt

```bash
source .venv/bin/activate
pip freeze > requirements.txt
```

Current Core Dependencies (Minimal):
```
matplotlib>=3.10.0
seaborn>=0.13.0
plotly>=6.3.0
mplfinance>=0.12.10b0
pandas>=2.3.0
numpy>=2.2.0
scipy>=1.16.0
pandas-ta>=0.4.71b0
statsmodels>=0.14.0
networkx>=3.5
squarify>=0.4.4
kaleido>=1.2.0
```

---

*Maintainers: finchart project group | Last Updated: 2025-01-17*
