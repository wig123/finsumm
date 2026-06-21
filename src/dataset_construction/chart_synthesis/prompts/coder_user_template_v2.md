# Coder User Prompt Template v2
# Enhanced Version: Programmatic Data Selection + LLM Generation of Question/Labels/Code

You are a professional financial data visualization engineer. Your goal is to:
1. Generate a professional **business question** (question) based on the data.
2. Design the chart **title and axis labels** (labels).
3. Generate chart code that **meets the standards of professional financial institutions**.

## Task
Use `{library}` to generate a `{chart_type}` chart.

## Data Information
- **Data Metrics**: `{indicator}`
- **Metric Description**: `{indicator_description}`
- **Data Source**: `{data_source}`
- **Topic Area**: `{theme}`
- **Language**: `{locale}`

## Data Preview (df variable is ready)
```
{dataframe_preview}
```

## Data Statistics
- Row Count: `{row_count}`
- Column Names: `{column_names}`
- Index: `{index_name}`
- **Time Range**: `{time_start}` ~ `{time_end}` (Total `{time_span_days}` days)
- Statistics: min=`{min_value}`, max=`{max_value}`, mean=`{mean_value}`, std=`{std_value}`
- Quantiles: q01=`{q01_value}`, q99=`{q99_value}`
{transform_hint}

## Output Requirements (JSON Format)

You must output a **valid JSON object** containing the following three fields:

```json
{{
  "question": "Business question based on the data (use {locale} language, like a financial analyst would ask)",
  "labels": {{
    "title": "Chart title ({locale} language, concise and clear)",
    "x_label": "X-axis label",
    "y_label": "Y-axis label"
  }},
  "code": "Complete Python plotting code (as a string, use \\n for line breaks)"
}}
```

### Question Requirements
- Use `{locale}` language.
- Pose professional questions as a financial analyst/researcher would.
- Be relevant to the data content and demonstrate analytical value.
- Example (Chinese locale): "How has the U.S. core inflation rate changed over the past five years? Has there been a clear trend shift?"
- Example (English): "How has the S&P 500 performed relative to its 200-day moving average over the past year?"

### Labels Requirements
- Use `{locale}` language.
- title: A concise description of the chart content, which can be conclusive or descriptive.
- x_label/y_label: Accurately describe the meaning of the axes, including units (if applicable).

### Code Requirements
1. Must define the function signature: `def plot_chart(df: pd.DataFrame):`
2. The function must return a visualization object (matplotlib.Figure / plotly.Figure / altair.Chart).
3. Use your generated title, x_label, and y_label.
4. Do not fetch data yourself; only use the provided df parameter.
5. **Semantic Consistency (CRITICAL)**: Titles, axis labels, and legends must match the actual data content.
6. **Font Configuration (CRITICAL)**: Add the following at the beginning of the function, before all plotting code:
```python
{font_config_code}
```

{library_specific_notes}

### Common Pandas Pitfalls (CRITICAL)
- ❌ Forbidden: `if df['col']:` or `if series:` — Series cannot be directly used as boolean values.
- ✅ Correct: `if df['col'].any():` or `if not df['col'].empty:`
- ❌ Forbidden: `df['A'] and df['B']` — Cannot connect Series with and/or.
- ✅ Correct: `(df['A'] > 0) & (df['B'] > 0)` — Use &/| and enclose in parentheses.

### Time Series X-axis Label Handling (CRITICAL)
**Applicable to**: matplotlib / seaborn / mplfinance

**Must** automatically select appropriate ticks based on the data's time span (see `time_span_days` above):
- **< 14 days**: `DayLocator(interval=1)` + `DateFormatter('%m-%d')`
- **14-90 days**: `WeekdayLocator(byweekday=MO)` or `DayLocator(interval=7)` + `DateFormatter('%m-%d')`
- **90-730 days**: `MonthLocator()` + `DateFormatter('%Y-%m')`
- **> 730 days**: `YearLocator()` or `MonthLocator(interval=3)` + `DateFormatter('%Y')`

**Best Practice**: Use `AutoDateLocator()` + `ConciseDateFormatter()` for automatic adaptation:
```python
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
locator = AutoDateLocator()
ax.xaxis.set_major_locator(locator)
ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
plt.xticks(rotation=45, ha='right')
```

❌ **Forbidden**: Using fixed intervals like `DayLocator(interval=2)` for long time series, which can lead to label stacking.

**Plotly/Altair**: These libraries automatically handle date axes, so manual Locator configuration is not required.

## Visual Style Guide: {visual_style_title}

{visual_style_notes}
{chart_constraints}
## Important Reminders
1. Output **valid JSON**, do not add markdown code block markers.
2. Use `\n` (single backslash) for line breaks in code, and `\"` for quotes.
3. Output the JSON object directly:
