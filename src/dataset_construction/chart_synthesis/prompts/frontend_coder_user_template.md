# Frontend Coder User Prompt Template

You are a professional financial data visualization engineer. Your goal is to generate charts **that meet the standards of professional financial institutions**.

## Task
**You MUST use the `{library}` library** to generate a `{chart_type}` chart.

**Important Constraint**: You **MUST and CAN ONLY** use the API of the `{library}` library. Do not use any other charting libraries (such as ECharts, D3, Highcharts, etc., unless it is the specified library). If you use the wrong library, the code will not run.

## Data (JSON format, injected into global variable window.chartData)
```json
{data_json}
```

## Data Information
- Number of data points: `{row_count}`
- Statistics: min=`{min_value}`, max=`{max_value}`, mean=`{mean_value}`, std=`{std_value}`
- Quantiles: q01=`{q01_value}`, q99=`{q99_value}`

## Language Configuration
- Language: `{locale}`
- Title: `{title}`
- X-axis label: `{x_label}`
- Y-axis label: `{y_label}`

## Code Requirements
1. You must define a function: `function renderChart(containerId, data)`
2. The function accepts a container ID and data, and renders the chart within the container.
3. Use the provided title and axis labels (`{locale}` language).
4. Do not fetch data yourself; only use the `data` parameter passed in.
5. Responsive design: The chart should adapt to the container size.
{library_specific_notes}

## Visual Style Guide: {visual_style_title}

{visual_style_notes}

### Core Principle: Subtractive Design

**Design Process**:
1. Start with the simplest chart (only data lines, axes, title, tooltip).
2. Review the chart and ask yourself: "Is anything obviously missing from this chart?"
3. Only add an element if the answer is "Yes."
4. After adding each element, ask: "What crucial information would be lost if this element were removed?"
   - If the answer is "Not much" or "It would just look better," do not add it.

**Evaluation Criteria**:
- Does this annotation help the reader **understand the data**, or is it **explaining the data**? The former is acceptable, the latter is not.
- Could a reader understand the main point of the chart within 5 seconds without this element? If yes, do not add it.
- Detailed numerical values should be displayed via tooltip on hover, not as static annotations.

### General Frontend Constraints
- Animation: Disabled (animation: false)
- Export button: Disabled
- X-axis label density: When data points > 30, you **must** control the number of X-axis labels to avoid overlap. Use the library's automatic date axis formatting feature or manually set intervals (e.g., display every 3 months).

## Library-Specific Configuration Reference

### ECharts
```javascript
{{
  animation: false,
  title: {{ text: '{title}', left: 'center', textStyle: {{ fontSize: 14 }} }},
  grid: {{ top: 60, right: 40, bottom: 60, left: 60 }},
  tooltip: {{ trigger: 'axis' }},
  // Do not use markPoint, markLine, markArea
}}
```

### Highcharts
```javascript
{{
  chart: {{ animation: false }},
  title: {{ text: '{title}' }},
  credits: {{ enabled: false }},
  exporting: {{ enabled: false }},
  plotOptions: {{ series: {{ animation: false }} }},
  // Do not use plotBands, plotLines, annotations, dataLabels
}}
```

### Chart.js
```javascript
{{
  animation: false,
  plugins: {{ legend: {{ display: false }} }}, // Single series does not need legend
  // Do not use annotation plugin
}}
```

### Plotly.js
```javascript
{{
  layout: {{
    title: '{title}',
    showlegend: false, // Single series does not need legend
    // Do not use shapes, annotations
  }},
  config: {{ displayModeBar: false }}
}}
```

## Evaluation Criteria
- Was the correct library used `{library}`?
- Is the chart sufficiently concise, with no redundant annotations?
- Are animations and export buttons disabled?
- Does it meet professional financial chart standards?

**Reminder**: You **MUST** use the `{library}` library to generate a concise and professional chart, and do not add any annotations.

Please output the complete JavaScript code directly, without including markdown formatting.
