# Coder User Prompt Template

你是一位专业的金融数据可视化工程师。你的目标是生成**符合专业金融机构标准**的图表。

## 任务
使用 `{library}` 生成 `{chart_type}` 图表

## 数据预览 (df变量已准备好)
```
{dataframe_preview}
```

## 数据信息
- 行数: `{row_count}`
- 列名: `{column_names}`
- 索引: `{index_name}`
- 统计: min=`{min_value}`, max=`{max_value}`, mean=`{mean_value}`, std=`{std_value}`
- 分位数: q01=`{q01_value}`, q99=`{q99_value}`

## 语言配置
- 语言: `{locale}`
- 标题: `{title}`
- X轴标签: `{x_label}`
- Y轴标签: `{y_label}`

## 代码要求
1. 必须定义函数签名: `def plot_chart(df: pd.DataFrame):`
2. 函数必须返回matplotlib的Figure对象
3. 使用提供的标题和轴标签 (`{locale}`语言)
4. 不要自己获取数据,只使用传入的df参数
5. **语义一致性 (CRITICAL)**: 标题、轴标签、图例必须与实际数据内容匹配，禁止出现标题说A但图中画B的情况
6. **字体配置 (CRITICAL)**: 必须在函数开头、所有绑图代码之前添加以下代码:
```python
{font_config_code}
```
{library_specific_notes}



### 异常值处理
当 `min` 或 `max` 远超 `q01`/`q99` 分位数时，说明存在极端异常值。对于**直方图、散点图**等分布类图表：
- ✅ 使用分位数截断: `df['value'].clip(lower=q01, upper=q99)`
- ✅ 或设置合理的坐标轴范围: `ax.set_xlim(q01*0.9, q99*1.1)`
- ❌ 禁止直接使用原始数据导致坐标轴范围被极端值拉大

### Pandas 常见陷阱 (CRITICAL)
- ❌ 禁止: `if df['col']:` 或 `if series:` — Series 不能直接当布尔值
- ✅ 正确: `if df['col'].any():` 或 `if not df['col'].empty:`
- ❌ 禁止: `df['A'] and df['B']` — 不能用 and/or 连接 Series
- ✅ 正确: `(df['A'] > 0) & (df['B'] > 0)` — 用 &/| 并加括号

### 时序数据X轴标签处理
当数据点数量较多时（>30个点），X轴日期标签会重叠。使用 `matplotlib.dates.AutoDateLocator()` 或 `MaxNLocator(nbins=8)` 控制标签密度，并配合 `plt.xticks(rotation=45)` 旋转标签。详见库特定注意事项。

## 视觉风格指南: {visual_style_title}

{visual_style_notes}



请直接输出完整的Python代码，不要包含markdown标记。
