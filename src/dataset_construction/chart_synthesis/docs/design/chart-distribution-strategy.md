# Financial Chart Dataset Distribution Strategy

## Core Principles

**Tiered Imbalanced Distribution** - Reflects real-world financial scenario usage frequency, ensuring core types are adequately trained and long-tail types are effectively covered.

---

## Recommended Distribution (10,000 Charts Baseline)

### Tier 1: Core Types (60%, 6000 Charts)

| Chart Type | Proportion | Quantity |
|------------|------------|----------|
| line | 12% | 1,200 |
| candlestick | 10% | 1,000 |
| bar | 10% | 1,000 |
| bar + line overlay | 8% | 800 |
| candlestick + volume | 8% | 800 |
| area | 5% | 500 |
| histogram | 4% | 400 |
| scatter | 3% | 300 |

### Tier 2: High-Frequency Analysis (25%, 2500 Charts)

| Chart Type | Proportion | Quantity |
|------------|------------|----------|
| heatmap | 5% | 500 |
| waterfall | 4% | 400 |
| OHLC | 3% | 300 |
| Bollinger Bands | 3% | 300 |
| box | 2.5% | 250 |
| pie | 2.5% | 250 |
| bubble | 2% | 200 |
| line + band overlay | 2% | 200 |
| treemap | 1% | 100 |

### Tier 3: Specialized Tools (10%, 1000 Charts)

| Chart Type | Proportion | Quantity |
|------------|------------|----------|
| contour | 2% | 200 |
| Fan Chart | 1.5% | 150 |
| Volume Profile | 1.5% | 150 |
| Ichimoku Cloud | 1.5% | 150 |
| Market Depth | 1% | 100 |
| Renko | 1% | 100 |
| errorbar | 0.8% | 80 |
| radar | 0.7% | 70 |

### Tier 4: Special Scenarios (5%, 500 Charts)

| Chart Type | Proportion | Quantity |
|------------|------------|----------|
| node | 1.5% | 150 |
| Gantt | 1% | 100 |
| Point & Figure | 1% | 100 |
| candlestick + indicator | 0.8% | 80 |
| waterfall + line | 0.7% | 70 |
| density | 0.5% | 50 |
| heatmap + scatter | 0.5% | 50 |

---

## Complete Type List (28 Types)

### Basic Types (15 types)
line, bar, candlestick, OHLC, area, scatter, pie, histogram, box, bubble, heatmap, waterfall, contour, treemap, radar

### Overlay Combinations (7 types)
bar + line, candlestick + volume, line + band (Bollinger), candlestick + indicator, waterfall + line, heatmap + scatter, Bollinger Bands

### Technical Analysis Specific (4 types)
Volume Profile, Ichimoku Cloud, Renko, Fan Chart

### Special Scenarios (6 types)
node (network graph), Gantt, Point & Figure, Market Depth, errorbar, density

---

## Key Constraints

- **Minimum Sample Size**: ≥70 charts per type (ensures training effectiveness)
- **Core Concentration**: Top 5 types account for 46% (line/candlestick/bar/overlay)
- **Long-Tail Coverage**: Low-frequency types retain basic samples (avoids zero-shot problem)

---

## Adjustment for Different Scales

| Dataset Scale | Tier1 | Tier2 | Tier3 | Tier4 | Min Samples/Type |
|---------------|-------|-------|-------|-------|------------------|
| 5K | 70% | 20% | 7% | 3% | 30 |
| **10K** ⭐ | **60%** | **25%** | **10%** | **5%** | **70** |
| 50K | 50% | 30% | 15% | 5% | 500 |

---

## Removed Types (vs. Original 29 Types in ECD)

**Reason for Removal**: Usage frequency in financial scenarios <1%

- quiver (vector field) - Physics use case
- 3d - Avoided in financial reports
- rose (rose chart) - Rarely applied
- funnel (funnel chart) - Marketing scenarios
- violin + box overlay - Overly complex

---

## Newly Added Types (vs. Original 29 Types in ECD)

**Newly Added Basic Types (3 types)**:
- Waterfall - Profit breakdown, cash flow analysis
- OHLC - Standard price chart in European and American markets
- Gantt - Project timeline, IPO progress

**Newly Added Overlay Combinations (3 types)**:
- candlestick + volume - Standard in trading software
- candlestick + indicator - Technical analysis (MA/EMA)
- waterfall + line - Cash flow trends

**Newly Added Technical Analysis Tools (5 types)**:
- Bollinger Bands - Volatility analysis
- Volume Profile - Price volume distribution
- Ichimoku Cloud - Ichimoku Cloud
- Fan Chart - Risk scenario analysis
- Market Depth - Order book visualization

**Newly Added Special Types (2 types)**:
- Renko - Denoised price chart
- Point & Figure - Classic technical analysis

---

## Validation Methods

1.  **Real-world Sampling Comparison**: Statistical analysis of chart type distribution in actual financial reports
2.  **Model Performance Monitoring**: Core type accuracy >85%, long-tail type accuracy >60%
3.  **A/B Testing**: Compare 60/25/10/5 vs 50/30/15/5 schemes

---

*Last Updated: 2025-01*
