# 图表类型技术栈映射

## 映射原则

- **Python库**: 每种图表类型选择最成熟/最简洁的实现库
- **前端库**: 优先选择金融领域广泛使用的可视化库
- **标准**: 优先选择原生支持、API稳定、文档完善的库

---

## Tier 1: 核心类型（60%, 6000张）

| 图表类型 | Python库 | 前端/JS库 |
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

## Tier 2: 高频分析（25%, 2500张）

| 图表类型 | Python库 | 前端/JS库 |
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

## Tier 3: 专业工具（10%, 1000张）

| 图表类型 | Python库 | 前端/JS库 |
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

## Tier 4: 特殊场景（5%, 500张）

| 图表类型 | Python库 | 前端/JS库 |
|---------|---------|----------|
| node | **networkx + matplotlib** | **D3.js** |
| Gantt | **plotly** | **Highcharts Gantt** |
| Point & Figure | **mplfinance** | **TradingView** |
| candlestick + indicator | **mplfinance** | **TradingView** |
| waterfall + line | **plotly** | **Highcharts** |
| density | **seaborn** | **Plotly.js** |
| heatmap + scatter | **seaborn** | **ECharts** |

---

## 库选择理由

### Python核心库

| 库名 | 适用场景 | 优势 |
|-----|---------|------|
| **matplotlib** | 基础图表、科学绘图 | 生态最成熟、文档完善、高度可定制 |
| **mplfinance** | 金融K线、技术指标 | 专为金融设计、一行代码生成K线+量柱 |
| **plotly** | 交互图表、复杂组合 | 原生支持双轴、子图布局、WebGL渲染 |
| **seaborn** | 统计可视化 | 高级API、美观默认样式、统计功能强 |
| **networkx** | 网络图布局 | 图论算法标准库 |

### 前端核心库

| 库名 | 适用场景 | 优势 |
|-----|---------|------|
| **ECharts** | 通用商业图表 | 中文文档、配置灵活、性能优秀、金融支持好 |
| **Highstock** | 金融时序图表 | K线图行业标准、缩放导航、实时更新 |
| **Highcharts** | 高级商业图表 | 瀑布图/甘特图原生支持、配置完善 |
| **TradingView** | 专业技术分析 | 金融行业标配、技术指标最全、实时行情 |
| **Plotly.js** | 科学/交互图表 | 与Python plotly同API、3D支持 |
| **D3.js** | 自定义复杂图表 | 底层控制力最强、网络图标准 |

---

## 技术栈组合建议

### 方案1: 开源优先
```
Python: matplotlib + mplfinance + seaborn + plotly
前端:   ECharts + Plotly.js + D3.js
成本:   免费
适合:   学术研究、开源项目
```

### 方案2: 金融专业 ⭐ 推荐
```
Python: mplfinance + matplotlib + plotly
前端:   Highstock + TradingView + ECharts
成本:   TradingView需商业授权
适合:   金融产品、量化平台
```

### 方案3: 全栈统一
```
Python: plotly
前端:   Plotly.js
成本:   免费（企业版收费）
适合:   快速原型、Python-JS一致性需求
```

---

## 实现优先级

### 第一阶段（核心8种）
matplotlib (line/bar/area/histogram/scatter) + mplfinance (candlestick/volume)

### 第二阶段（高频9种）
seaborn (heatmap/box) + plotly (waterfall/treemap/overlay)

### 第三阶段（专业8种）
mplfinance (OHLC/Bollinger/Ichimoku/Renko) + matplotlib (contour/fan/errorbar)

### 第四阶段（特殊3种）
plotly (gantt/depth) + networkx (node)

---

*更新时间: 2025-01*
