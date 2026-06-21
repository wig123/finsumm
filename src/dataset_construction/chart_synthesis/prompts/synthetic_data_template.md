# Synthetic Data Generator Prompt

You are a financial data expert. Generate simulated data with real-world characteristics based on a business problem.

## Business Problem
{question}

## Data Requirements
- Data Shape: {shape}
- Chart Type: {chart_type}
- Theme Domain: {theme}
- Language: {language}

## Data Scale Reference
- **Pie Chart/Waterfall Chart**: **4-10** categories
- **Radar Chart**: **5-8** dimensions
- **Scatter Plot/Bubble Chart**: **8-30** data points
- **Box Plot**: **15-30** data points per group (outliers should be included)
- **Heatmap/Matrix**: **5x5** to **12x12** matrix
- **Treemap**: **8-20** nodes
- **Time Series**: **12-90** time points (12 points/year for monthly, ~60 points/quarter for daily)
- **Sankey Diagram/Flow Diagram**: **3-8** sources and **3-8** targets
- **Bar Chart/Column Chart**: **5-15** categories

## Output Format (Important! Choose the correct format based on the data shape)

### If shape is TS_1D (Time Series 1D):
```json
{
  "data": [
    {"date": "2024-01-01", "value": numeric_value},
    {"date": "2024-02-01", "value": numeric_value},
    ...
  ],
  "metadata": {
    "unit": "data unit",
    "source": "simulated data"
  }
}
```

### If shape is CS_1D (Cross-Sectional 1D):
```json
{
  "data": [
    {"entity": "entity name", "value": numeric_value},
    {"entity": "entity name", "value": numeric_value},
    ...
  ],
  "metadata": {
    "unit": "data unit",
    "source": "simulated data"
  }
}
```

### If shape is CS_ND (Cross-Sectional ND) or MATRIX:
```json
{
  "data": [
    {"entity": "entity name", "var1": numeric_value, "var2": numeric_value, ...},
    ...
  ],
  "metadata": {
    "unit": "data unit",
    "source": "simulated data"
  }
}
```

### If shape is FLOW (Flow data, e.g., Sankey Diagram):
```json
{
  "data": [
    {"source": "source", "target": "target", "value": numeric_value},
    ...
  ],
  "metadata": {
    "unit": "data unit",
    "source": "simulated data"
  }
}
```

## Generation Requirements
1. **Realism**: Numerical ranges and distributions should align with real-world characteristics.
2. **Diversity**: There should be reasonable differences between entities (e.g., developed countries vs. emerging markets, large companies vs. small companies).
3. **Correlation**: Variables should have reasonable correlations (e.g., high growth is often accompanied by high valuation).
4. **Noise**: Do not generate perfect textbook data; include realistic random fluctuations.
5. **Consistency**: The data should be consistent with the description of the business problem.
6. **Data Volume**: Refer to the suggestions above and determine an appropriate data volume based on the chart type.

## Language Requirements
- If language is zh-CN, use Chinese for entity names (e.g., China, USA, Apple Inc.).
- If language is en-US, use English for entity names (e.g., China, USA, Apple Inc.).

Please output JSON directly, without including markdown formatting.
