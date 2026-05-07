# Coder User Prompt Template v2
# 增强版：程序化数据选择 + LLM 生成 question/labels/code

你是一位专业的金融数据可视化工程师。你的目标是：
1. 根据数据生成一个专业的**业务问题** (question)
2. 设计图表的**标题和轴标签** (labels)
3. 生成**符合专业金融机构标准**的图表代码

## 任务
使用 `{library}` 生成 `{chart_type}` 图表

## 数据信息
- **数据指标**: `{indicator}`
- **指标描述**: `{indicator_description}`
- **数据源**: `{data_source}`
- **主题领域**: `{theme}`
- **语言**: `{locale}`

## 数据预览 (df变量已准备好)
```
{dataframe_preview}
```

## 数据统计
- 行数: `{row_count}`
- 列名: `{column_names}`
- 索引: `{index_name}`
- **时间范围**: `{time_start}` ~ `{time_end}` (共 `{time_span_days}` 天)
- 统计: min=`{min_value}`, max=`{max_value}`, mean=`{mean_value}`, std=`{std_value}`
- 分位数: q01=`{q01_value}`, q99=`{q99_value}`
{transform_hint}

## 输出要求 (JSON 格式)

你必须输出一个**有效的 JSON 对象**，包含以下三个字段：

```json
{{
  "question": "基于数据的业务问题（使用{locale}语言，像金融分析师会问的问题）",
  "labels": {{
    "title": "图表标题（{locale}语言，简洁明了）",
    "x_label": "X轴标签",
    "y_label": "Y轴标签"
  }},
  "code": "完整的Python绘图代码（字符串形式，换行用\\n）"
}}
```

### question 要求
- 使用 `{locale}` 语言
- 像金融分析师/研究员会提出的专业问题
- 与数据内容相关，体现分析价值
- 示例 (中文): "过去5年美国核心通胀率的走势如何？是否出现明显的趋势性变化？"
- 示例 (英文): "How has the S&P 500 performed relative to its 200-day moving average over the past year?"

### labels 要求
- 使用 `{locale}` 语言
- title: 简洁描述图表内容，可以是结论型或描述型
- x_label/y_label: 准确描述轴含义，包含单位（如适用）

### code 要求
1. 必须定义函数签名: `def plot_chart(df: pd.DataFrame):`
2. 函数必须返回可视化对象（matplotlib.Figure / plotly.Figure / altair.Chart）
3. 使用你生成的 title、x_label、y_label
4. 不要自己获取数据，只使用传入的 df 参数
5. **语义一致性 (CRITICAL)**: 标题、轴标签、图例必须与实际数据内容匹配
6. **字体配置 (CRITICAL)**: 必须在函数开头、所有绑图代码之前添加：
```python
{font_config_code}
```

{library_specific_notes}

### Pandas 常见陷阱 (CRITICAL)
- ❌ 禁止: `if df['col']:` 或 `if series:` — Series 不能直接当布尔值
- ✅ 正确: `if df['col'].any():` 或 `if not df['col'].empty:`
- ❌ 禁止: `df['A'] and df['B']` — 不能用 and/or 连接 Series
- ✅ 正确: `(df['A'] > 0) & (df['B'] > 0)` — 用 &/| 并加括号

### 时序数据X轴标签处理 (CRITICAL)
**适用于**: matplotlib / seaborn / mplfinance

**必须**根据数据时间跨度（见上方 `time_span_days`）自动选择合适的刻度：
- **< 14天**: `DayLocator(interval=1)` + `DateFormatter('%m-%d')`
- **14-90天**: `WeekdayLocator(byweekday=MO)` 或 `DayLocator(interval=7)` + `DateFormatter('%m-%d')`
- **90-730天**: `MonthLocator()` + `DateFormatter('%Y-%m')`
- **> 730天**: `YearLocator()` 或 `MonthLocator(interval=3)` + `DateFormatter('%Y')`

**最佳实践**：使用 `AutoDateLocator()` + `ConciseDateFormatter()` 自动适配：
```python
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
locator = AutoDateLocator()
ax.xaxis.set_major_locator(locator)
ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
plt.xticks(rotation=45, ha='right')
```

❌ **禁止**：对长时间序列使用固定间隔如 `DayLocator(interval=2)`，会导致标签堆叠

**Plotly/Altair**: 这些库会自动处理日期轴，无需手动配置 Locator

## 视觉风格指南: {visual_style_title}

{visual_style_notes}
{chart_constraints}
## 重要提醒
1. 输出**有效 JSON**，不要添加 markdown 代码块标记
2. code 中换行用 `\n`（单反斜杠），引号用 `\"`
3. 直接输出 JSON 对象：

