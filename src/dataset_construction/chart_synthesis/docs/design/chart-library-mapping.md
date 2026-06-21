# Chart Type Tech Stack Mapping

## Mapping Principles

- **Python Libraries**: Select the most mature/concise implementation library for each chart type.
- **Frontend Libraries**: Prioritize visualization libraries widely used in the financial domain.
- **Standards**: Prioritize libraries with native support, stable APIs, and comprehensive documentation.

---

## Tier 1: Core Types (60%, 6000 Charts)

| Chart Type | Python Library | Frontend/JS Library |
|---------|---------|----------|
| line | **matplotlib** | **ECharts** |
| candlestick | **mplfinance** | **Highstock** |
| bar | **matplotlib** | **ECharts** |
| bar + line overlay | **plotly** | **ECharts** |
| candlestick + volume | **mplfinance** | **Highstock** |
| area | **matplotlib** | **ECharts** |
| histogram | **matplotlib** | **ECharts** |
| scatter | **matplotlib** | **ECharts** |

---

## Tier 2: High-Frequency Analysis (25%, 2500 Charts)

| Chart Type | Python Library | Frontend/JS Library |
|---------|---------|----------|
| heatmap | **seaborn** | **ECharts** |
| waterfall | **plotly** | **Highcharts** |
| OHLC | **mplfinance** | **Highstock** |
| Bollinger Bands | **mplfinance** | **TradingView** |
| box | **seaborn** | **ECharts** |
| pie | **matplotlib** | **ECharts** |
| bubble | **matplotlib** | **ECharts** |
| line + band overlay | **matplotlib** | **Highcharts** |
| treemap | **plotly** | **ECharts** |

---

## Tier 3: Specialized Tools (10%, 1000 Charts)

| Chart Type | Python Library | Frontend/JS Library |
|---------|---------|----------|
| contour | **matplotlib** | **Plotly.js** |
| Fan Chart | **matplotlib** | **Highcharts** |
| Volume Profile | **matplotlib** | **TradingView** |
| Ichimoku Cloud | **mplfinance** | **TradingView** |
| Market Depth | **plotly** | **TradingView** |
| Renko | **mplfinance** | **TradingView** |
| errorbar | **matplotlib** | **Highcharts** |
| radar | **plotly** | **ECharts** |

---

## Tier 4: Special Scenarios (5%, 500 Charts)

| Chart Type | Python Library | Frontend/JS Library |
|---------|---------|----------|
| node | **networkx + matplotlib** | **D3.js** |
| Gantt | **plotly** | **Highcharts Gantt** |
| Point & Figure | **mplfinance** | **TradingView** |
| candlestick + indicator | **mplfinance** | **TradingView** |
| waterfall + line | **plotly** | **Highcharts** |
| density | **seaborn** | **Plotly.js** |
| heatmap + scatter | **seaborn** | **ECharts** |

---

## Library Selection Rationale

### Python Core Libraries

| Library Name | Applicable Scenarios | Advantages |
|-----|---------|------|
| **matplotlib** | Basic charts, scientific plotting | Most mature ecosystem, comprehensive documentation, highly customizable |
| **mplfinance** | Financial candlestick charts, technical indicators | Designed for finance, one line of code generates candlestick + volume bars |
| **plotly** | Interactive charts, complex combinations | Native support for dual axes, subplot layouts, WebGL rendering |
| **seaborn** | Statistical visualization | High-level API, aesthetic default styles, strong statistical capabilities |
| **networkx** | Network graph layout | Standard library for graph theory algorithms |

### Frontend Core Libraries

| Library Name | Applicable Scenarios | Advantages |
|-----|---------|------|
| **ECharts** | General business charts | Chinese documentation, flexible configuration, excellent performance, good financial support |
| **Highstock** | Financial time series charts | Industry standard for candlestick charts, zoom navigation, real-time updates |
| **Highcharts** | Advanced business charts | Native support for waterfall/Gantt charts, comprehensive configuration |
| **TradingView** | Professional technical analysis | Financial industry standard, most comprehensive technical indicators, real-time market data |
| **Plotly.js** | Scientific/interactive charts | Same API as Python Plotly, 3D support |
| **D3.js** | Custom complex charts | Strongest low-level control, network graph standard |

---

## Tech Stack Combination Suggestions

### Solution 1: Open Source First
```
Python:   matplotlib + mplfinance + seaborn + plotly
Frontend: ECharts + Plotly.js + D3.js
Cost:     Free
Suitable: Academic research, open source projects
```

### Solution 2: Financial Professional ⭐ Recommended
```
Python:   mplfinance + matplotlib + plotly
Frontend: Highstock + TradingView + ECharts
Cost:     TradingView requires commercial license
Suitable: Financial products, quantitative platforms
```

### Solution 3: Full-Stack Unification
```
Python:   plotly
Frontend: Plotly.js
Cost:     Free (enterprise version paid)
Suitable: Rapid prototyping, Python-JS consistency requirements
```

---

## Implementation Priority

### Phase 1 (8 Core Types)
matplotlib (line/bar/area/histogram/scatter) + mplfinance (candlestick/volume)

### Phase 2 (9 High-Frequency Types)
seaborn (heatmap/box) + plotly (waterfall/treemap/overlay)

### Phase 3 (8 Specialized Types)
mplfinance (OHLC/Bollinger/Ichimoku/Renko) + matplotlib (contour/fan/errorbar)

### Phase 4 (3 Special Types)
plotly (gantt/depth) + networkx (node)

---

*Last Updated: 2025-01*
