# FinChartSum Benchmark Data

## Overview

FinChartSum is a benchmark for evaluating structured financial chart summarization. It contains **~1,000 samples** across diverse chart types and financial topics, with human-annotated four-part structured summaries.

## Benchmark Composition

| Subset | Count | Source | Language |
|--------|-------|--------|----------|
| Real-world English | 200 | FinChart-Bench | English |
| FinMME samples | 200 | FinMME | English |
| Synthesized Chinese | 300 | Code-assisted | Chinese |
| Synthesized English | 300 | Code-assisted | English |
| **Total** | **~1,000** | | Bilingual |

## Sample Data

`finchartsum_sample.json` contains **50 representative samples** from the benchmark for review purposes.

Each sample includes:

| Field | Description |
|-------|-------------|
| `id` | Unique sample identifier |
| `chart_type` | Financial chart type (e.g., candlestick, line, heatmap) |
| `topic` | Financial topic (e.g., equity markets, forex, fixed income) |
| `language` | Language of the summary (en / zh) |
| `source` | Data source subset |
| `ground_truth` | Human-annotated four-part structured summary |

## Four-Part Structured Summary Format

Each summary follows a semantic model with four levels. English samples use bracket headers, Chinese samples use full-width bracket headers:

| English Header | Chinese Header | Description |
|:---------------|:---------------|:------------|
| [Chart Components] | 【图表构成】 | Chart type, axes, legend, visual encoding |
| [Data Relationships] | 【数据关系】 | Core numerical values, extrema, comparisons |
| [Pattern Characteristics] | 【模式特征】 | Overall trajectory, phase characteristics, anomalies |
| [Core Insights] | 【核心洞察】 | Business interpretation, risk assessment |

## Chart Type Distribution

The benchmark covers **33 chart types** organized into 4 priority tiers across **20 financial topics**.

## Full Dataset Release

The complete dataset, including all chart images and annotations, will be released upon paper acceptance to ensure reproducibility.
