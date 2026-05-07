# LLM 提示词模板

本目录包含 Chart Synthesis Pipeline 使用的所有 LLM 提示词模板。

## 📁 文件说明

### Planner (Layer 1 - 业务规划)
使用模型: **GPT-5** (API易)

- **planner_system.txt** - System Prompt
  ```
  你是一个专业的金融图表规划专家,只输出JSON格式,不包含任何markdown标记。
  ```

- **planner_user_template.md** - User Prompt 模板
  - 输入变量: `chart_type`, `language`, `theme`, `task` 等
  - 输出格式: JSON (question, data_requirement, labels, style_intent)
  - 核心功能: 根据业务需求规划图表的数据选择和样式意图

### Coder (Layer 4 - 代码生成)
使用模型: **Claude Sonnet 4.5** (API易)

- **coder_system.txt** - System Prompt
  ```
  你是一个专业的Python数据可视化工程师,只输出Python代码,不包含markdown标记。
  ```

- **coder_user_template.md** - User Prompt 模板
  - 输入变量: `library`, `chart_type`, `dataframe_preview`, `style_intent` 等
  - 输出格式: Python代码 (def plot_chart(df))
  - 核心功能: 根据数据特征和样式意图生成可视化代码

## 🔍 提示词设计原则

### 1. 模块化分离
- **System Prompt**: 角色定义 + 输出格式约束
- **User Prompt**: 具体任务描述 + 上下文信息

### 2. 灵活绘制模式 (v0.3.0)
- **Planner**: 生成详细的 `style_intent` 描述可视化意图
- **Coder**: 根据 `style_intent` 和数据特征自主决策具体实现
- **优势**: 避免硬编码标注,模型智能选择可视化元素

### 3. 约束与引导
- **数据源映射**: FRED/AKShare/横截面数据源的明确规则
- **输出格式**: JSON Schema 或代码结构的明确要求
- **评判标准**: 信噪比、专业性、美观度等评估维度

## 📊 提示词变量说明

### Planner 变量 (动态填充)
```python
{
    "chart_type": "candlestick",              # 图表类型
    "language": "zh-CN",                      # 语言
    "theme": "commodities",                   # 主题代码
    "theme_label": "大宗商品",                # 主题标签
    "theme_description": "原油、天然气...",    # 主题描述
    "task": "monitor",                        # 任务代码
    "task_label": "监测",                     # 任务标签
    "preferred_indicators": [...],            # 优先指标列表
    "typical_data_sources": [...],            # 典型数据源
    "shape_preference": ["TS_1D"],            # 建议数据形态
    "frequency": ["D", "W"],                  # 建议频率
    "time_horizon": ["5Y", "10Y"],            # 建议时间范围
    "style_hints": [...]                      # 样式提示
}
```

### Coder 变量 (动态填充)
```python
{
    "library": "mplfinance",                  # 绘图库
    "chart_type": "candlestick",              # 图表类型
    "dataframe_preview": "...",               # 数据预览 (df.head(10))
    "row_count": 740,                         # 行数
    "column_names": ["value"],                # 列名
    "index_name": "date",                     # 索引名
    "min_value": 58.29,                       # 最小值
    "max_value": 93.67,                       # 最大值
    "mean_value": 74.02,                      # 均值
    "locale": "zh-CN",                        # 语言
    "title": "WTI原油价格...",                # 标题
    "x_label": "日期",                        # X轴标签
    "y_label": "价格 (美元/桶)",              # Y轴标签
    "style_intent": "...",                    # 样式意图 (来自Planner)
    "font_config_code": "...",                # 中文字体配置代码
    "font_config_instruction": "..."          # 字体配置说明
}
```

## 🔄 实际使用流程

### 1. Planner 提示词构建
```python
# src/capabilities/chart_planning/planner.py:50-175
def build_prompt(planner_input, error_context=None):
    # 1. 加载 theme 和 task 配置
    theme_config = load_theme_mapping(planner_input.theme)
    task_config = load_task_mapping(planner_input.task)

    # 2. 填充模板变量
    prompt = planner_user_template.format(
        chart_type=planner_input.chart_type,
        language=planner_input.language,
        theme_label=theme_config["label"],
        # ... 其他变量
    )

    # 3. 附加错误上下文 (重试时)
    if error_context:
        prompt += f"\n\n**上次错误**: {error_context}"

    return prompt
```

### 2. Coder 提示词构建
```python
# src/capabilities/chart_rendering/renderer.py:42-155
def build_prompt(dataspec, df, error_context=None):
    # 1. 提取数据特征
    dataframe_preview = df.head(10).to_string()
    min_value = df['value'].min()
    max_value = df['value'].max()

    # 2. 准备字体配置 (中文)
    if locale == "zh-CN":
        font_config_code = "matplotlib.rcParams['font.sans-serif'] = ..."

    # 3. 填充模板变量
    prompt = coder_user_template.format(
        library=dataspec.library_config.python_lib,
        chart_type=dataspec.chart_type,
        dataframe_preview=dataframe_preview,
        style_intent=dataspec.output.style_intent,
        # ... 其他变量
    )

    # 4. 附加错误上下文 (重试时)
    if error_context:
        prompt += f"\n\n**上次错误**: {error_context}"

    return prompt
```

## 📝 提示词优化历史

### v0.3.0 (2025-11-18) - 灵活绘制模式
- **移除**: 硬编码的 `annotations` 配置
- **增强**: `style_intent` 作为核心沟通桥梁
- **新增**: Coder 的设计原则、可视化元素库、评判标准
- **优化**: Planner 的 style_intent 编写指南 (良好/不良示例)

### v0.2.0 (2025-11-17) - 横截面数据支持
- **新增**: 横截面数据源映射 (国家统计局、IMF、世界银行、FAO)
- **新增**: 数据形态 CS_1D, CS_ND 说明

### v0.1.0 (2025-01-17) - 初始版本
- **基础**: Planner/Coder 双LLM提示词架构
- **核心**: JSON输出格式、数据源映射、代码结构要求

## 🔧 如何修改提示词

### 1. 直接修改模板文件
```bash
# 编辑 Planner 用户提示词
vim prompts/planner_user_template.md

# 编辑 Coder 用户提示词
vim prompts/coder_user_template.md
```

### 2. 同步到代码
修改模板后,需要同步更新代码中的 `build_prompt()` 方法:
- `src/capabilities/chart_planning/planner.py`
- `src/capabilities/chart_rendering/renderer.py`

### 3. 测试验证
```bash
# 单次测试
python scripts/run_batch.py --config batch_configs/demo.yaml

# 查看生成的完整提示词
cat batch_output/demo/*/prompts/planner_llm_trace.json | jq '.messages'
cat batch_output/demo/*/prompts/coder_llm_trace.json | jq '.messages'
```

## 📖 参考资料

### 提示词工程最佳实践
- **角色定位**: "你是一位专业的..." 明确专业身份
- **任务分解**: 将复杂任务拆解为清晰的步骤
- **示例引导**: 提供良好/不良示例对比
- **约束明确**: 明确输出格式、数据源规则等约束
- **上下文完整**: 提供足够的数据预览和配置信息

### LLM 配置
```yaml
# config/llm_config.yaml
pipeline_models:
  planner:
    provider: "apiyi"
    model: "gpt-5"
    temperature: 0.7          # 较高温度,鼓励创造性
    max_tokens: 8000          # 足够生成详细 style_intent

  coder:
    provider: "apiyi"
    model: "claude-sonnet-4-5-20250929"
    temperature: 0.3          # 较低温度,确保代码准确性
    max_tokens: 4000
```

---

**维护者**: Chart Synthesis Team
**最后更新**: 2025-11-19
**版本**: v0.3.0
