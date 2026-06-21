# LLM Prompt Templates

This directory contains all LLM prompt templates used by the Chart Synthesis Pipeline.

## 📁 File Descriptions

### Planner (Layer 1 - Business Planning)
Model Used: **GPT-5** (API Key: `easylm`)

- **planner_system.txt** - System Prompt
  ```
  You are a professional financial chart planning expert. Output only JSON format without any markdown markers.
  ```

- **planner_user_template.md** - User Prompt Template
  - Input Variables: `chart_type`, `language`, `theme`, `task`, etc.
  - Output Format: JSON (question, data_requirement, labels, style_intent)
  - Core Function: Plan chart data selection and style intent based on business requirements.

### Coder (Layer 4 - Code Generation)
Model Used: **Claude Sonnet 4.5** (API Key: `easylm`)

- **coder_system.txt** - System Prompt
  ```
  You are a professional Python data visualization engineer. Output only Python code without markdown markers.
  ```

- **coder_user_template.md** - User Prompt Template
  - Input Variables: `library`, `chart_type`, `dataframe_preview`, `style_intent`, etc.
  - Output Format: Python code (def plot_chart(df))
  - Core Function: Generate visualization code based on data characteristics and style intent.

## 🔍 Prompt Design Principles

### 1. Modular Separation
- **System Prompt**: Role definition + Output format constraints.
- **User Prompt**: Specific task description + Contextual information.

### 2. Flexible Rendering Mode (v0.3.0)
- **Planner**: Generates a detailed `style_intent` describing visualization intent.
- **Coder**: Independently decides on specific implementation based on `style_intent` and data characteristics.
- **Advantages**: Avoids hardcoded annotations, enabling intelligent model selection of visualization elements.

### 3. Constraints and Guidance
- **Data Source Mapping**: Clear rules for FRED/AKShare/Cross-sectional data sources.
- **Output Format**: Explicit requirements for JSON Schema or code structure.
- **Evaluation Criteria**: Dimensions such as signal-to-noise ratio, professionalism, and aesthetics.

## 📊 Prompt Variable Descriptions

### Planner Variables (Dynamically Populated)
```python
{
    "chart_type": "candlestick",              # Chart type
    "language": "zh-CN",                      # Language
    "theme": "commodities",                   # Theme code
    "theme_label": "Commodities",             # Theme label
    "theme_description": "Crude oil, natural gas...",  # Theme description
    "task": "monitor",                        # Task code
    "task_label": "Monitoring",               # Task label
    "preferred_indicators": [...],            # Preferred indicator list
    "typical_data_sources": [...],            # Typical data sources
    "shape_preference": ["TS_1D"],            # Recommended data shape
    "frequency": ["D", "W"],                  # Recommended frequency
    "time_horizon": ["5Y", "10Y"],            # Recommended time range
    "style_hints": [...]                      # Style hints
}
```

### Coder Variables (Dynamically Populated)
```python
{
    "library": "mplfinance",                  # Plotting library
    "chart_type": "candlestick",              # Chart type
    "dataframe_preview": "...",               # Data preview (df.head(10))
    "row_count": 740,                         # Row count
    "column_names": ["value"],                # Column names
    "index_name": "date",                     # Index name
    "min_value": 58.29,                       # Minimum value
    "max_value": 93.67,                       # Maximum value
    "mean_value": 74.02,                      # Mean value
    "locale": "zh-CN",                        # Language
    "title": "WTI Crude Oil Price...",        # Title
    "x_label": "Date",                        # X-axis label
    "y_label": "Price (USD/barrel)",          # Y-axis label
    "style_intent": "...",                    # Style intent (from Planner)
    "font_config_code": "...",                # Chinese font configuration code
    "font_config_instruction": "..."          # Font configuration instructions
}
```

## 🔄 Actual Usage Flow

### 1. Planner Prompt Construction
```python
# src/capabilities/chart_planning/planner.py:50-175
def build_prompt(planner_input, error_context=None):
    # 1. Load theme and task configurations
    theme_config = load_theme_mapping(planner_input.theme)
    task_config = load_task_mapping(planner_input.task)

    # 2. Fill template variables
    prompt = planner_user_template.format(
        chart_type=planner_input.chart_type,
        language=planner_input.language,
        theme_label=theme_config["label"],
        # ... other variables
    )

    # 3. Append error context (on retry)
    if error_context:
        prompt += f"\n\n**Previous Error**: {error_context}"

    return prompt
```

### 2. Coder Prompt Construction
```python
# src/capabilities/chart_rendering/renderer.py:42-155
def build_prompt(dataspec, df, error_context=None):
    # 1. Extract data features
    dataframe_preview = df.head(10).to_string()
    min_value = df['value'].min()
    max_value = df['value'].max()

    # 2. Prepare font configuration (Chinese)
    if locale == "zh-CN":
        font_config_code = "matplotlib.rcParams['font.sans-serif'] = ..."

    # 3. Fill template variables
    prompt = coder_user_template.format(
        library=dataspec.library_config.python_lib,
        chart_type=dataspec.chart_type,
        dataframe_preview=dataframe_preview,
        style_intent=dataspec.output.style_intent,
        # ... other variables
    )

    # 4. Append error context (on retry)
    if error_context:
        prompt += f"\n\n**Previous Error**: {error_context}"

    return prompt
```

## 📝 Prompt Optimization History

### v0.3.0 (2025-11-18) - Flexible Rendering Mode
- **Removed**: Hardcoded `annotations` configurations.
- **Enhanced**: `style_intent` as the core communication bridge.
- **Added**: Coder design principles, visualization element library, and evaluation criteria.
- **Optimized**: Planner's `style_intent` writing guidelines (good/bad examples).

### v0.2.0 (2025-11-17) - Cross-sectional Data Support
- **Added**: Cross-sectional data source mapping (National Bureau of Statistics, IMF, World Bank, FAO).
- **Added**: Explanations for data formats CS_1D, CS_ND.

### v0.1.0 (2025-01-17) - Initial Version
- **Foundation**: Dual LLM prompt architecture for Planner/Coder.
- **Core**: JSON output format, data source mapping, and code structure requirements.

## 🔧 How to Modify Prompts

### 1. Directly Modify Template Files
```bash
# Edit Planner user prompt
vim prompts/planner_user_template.md

# Edit Coder user prompt
vim prompts/coder_user_template.md
```

### 2. Synchronize to Code
After modifying templates, you need to update the `build_prompt()` method in the code:
- `src/capabilities/chart_planning/planner.py`
- `src/capabilities/chart_rendering/renderer.py`

### 3. Test and Verify
```bash
# Single test
python scripts/run_batch.py --config batch_configs/demo.yaml

# View generated complete prompts
cat batch_output/demo/*/prompts/planner_llm_trace.json | jq '.messages'
cat batch_output/demo/*/prompts/coder_llm_trace.json | jq '.messages'
```

## 📖 References

### Prompt Engineering Best Practices
- **Role Definition**: "You are a professional..." Clearly define the professional identity.
- **Task Decomposition**: Break down complex tasks into clear steps.
- **Example Guidance**: Provide comparisons of good/bad examples.
- **Clear Constraints**: Specify output formats, data source rules, etc.
- **Complete Context**: Provide sufficient data previews and configuration information.

### LLM Configuration
```yaml
# config/llm_config.yaml
pipeline_models:
  planner:
    provider: "apiyi"
    model: "gpt-5"
    temperature: 0.7          # Higher temperature, encourages creativity
    max_tokens: 8000          # Sufficient for generating detailed style_intent

  coder:
    provider: "apiyi"
    model: "claude-sonnet-4-5-20250929"
    temperature: 0.3          # Lower temperature, ensures code accuracy
    max_tokens: 4000
```

---

**Maintainers**: Chart Synthesis Team
**Last Updated**: 2025-11-19
**Version**: v0.3.0

---
