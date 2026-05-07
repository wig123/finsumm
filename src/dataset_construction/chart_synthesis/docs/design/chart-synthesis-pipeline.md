# 金融图表合成Pipeline

## 概述

端到端的金融图表数据生成流程,从业务需求到最终图表+总结的完整Pipeline。

**核心特性**:
- 输入端控制图表类型和语言分布
- 使用真实金融数据源 (FRED/AKShare)
- LLM驱动的代码生成和总结撰写
- 支持28种图表类型,双语输出 (中文/英文)

---

## Pipeline架构

```
[外部控制层] 生成采样计划
    ↓ {chart_type, language, theme, role, task}

[Layer 1] Planner LLM - 业务规划
    ↓ question + data_requirement + labels

[Layer 2] DataSpec编译 - 规范化
    ↓ 完整DataSpec (六维正交)

[Layer 3] 数据准备 - 真实数据
    ↓ DataFrame + LLM Payload

[Layer 4] Coder LLM - 代码生成
    ↓ Python/JS代码 + 图片

[Layer 5] Narrator LLM - 总结生成
    ↓ 自然语言描述
```

---

## 核心概念

### 1. DataSpec (六维正交)

数据需求的标准化描述,包含六个正交维度:

| 维度 | 说明 | 示例 |
|------|------|------|
| **Shape** | 数据形态 | `TS_1D` (单变量时序), `CS_1D` (单变量横截面) |
| **What** | 测量对象 | 指标 (CPI同比), 数据源 (FRED), 序列代码 |
| **Where** | 测量范围 | 实体类型 (国家), 实体列表 ([US, CN]) |
| **When** | 时间维度 | 时间区间 (最近20年), 频率 (月度) |
| **How** | 数据变换 | 变换方式 (同比), 调整 (季调) |
| **LLM_Payload** | 给LLM的数据策略 | 长时序降维, 短时序/横截面保留原始 |

**扩展阅读**: 详细DataSpec规范见 `dataspec-specification.md` (待创建)

---

### 2. 图表类型分布

基于真实金融场景使用频率的分层分布:

- **Tier 1 (60%)**: 核心类型 - line, candlestick, bar, area, histogram, scatter
- **Tier 2 (25%)**: 高频分析 - heatmap, waterfall, OHLC, Bollinger Bands, box, pie
- **Tier 3 (10%)**: 专业工具 - contour, Fan Chart, Volume Profile, Ichimoku Cloud
- **Tier 4 (5%)**: 特殊场景 - node, Gantt, Point & Figure

**参考文档**: `chart-distribution-strategy.md`

---

### 3. 图表类型到绘图库的映射

每种图表类型预定义最佳绘图库:

| 图表类型 | Python库 | 前端库 | Tier |
|---------|---------|--------|------|
| line | matplotlib | ECharts | 1 |
| candlestick | mplfinance | Highstock | 1 |
| heatmap | seaborn | ECharts | 2 |
| waterfall | plotly | Highcharts | 2 |

**参考文档**: `chart-library-mapping.md`

---

### 4. 数据源

7个真实数据源,覆盖时序和横截面:

**时序数据**:
- **FRED** (13个序列): 美国宏观/商品/能源数据
- **AKShare** (11个接口): 中国农产品/能源/宏观数据

**横截面数据**:
- 国家统计局, IMF, UN Comtrade, FAOSTAT, 世界银行

**参考文档**: `../test/data_sources_test/README.md`

---

## 关键流程

### 外部控制层 → Planner输入

**输入端直接指定**:
```json
{
  "chart_type": "line",        // 从28种中指定
  "language": "zh-CN",         // zh-CN | en-US
  "theme": "macro",            // 8大主题
  "role": "macro_strategist",  // 7种角色
  "task": "trend"              // 8类任务
}
```

**由外部控制层负责**:
- 按`chart-distribution-strategy.md`权重采样图表类型
- 按比例采样语言 (建议 60% zh-CN, 40% en-US)
- 组合Theme × Role × Task (考虑兼容性)

---

### Planner LLM → 业务规划

**职责**: 根据指定配置生成业务逻辑

**输出**:
```json
{
  "question": "过去20年美国通胀趋势如何?",
  "data_requirement": {
    "indicator": "macro.inflation.cpi.headline",
    "entities": ["US"],
    "time_horizon": "20Y",
    "frequency": "M",
    "data_source": "FRED"
  },
  "labels": {
    "title": "美国CPI同比走势(2005-2025)",
    "x_label": "日期",
    "y_label": "同比增速(%)"
  },
  "style_intent": "宏观研究报告风格,标注关键节点",
  "annotations": ["last_value", "max", "min"]
}
```

**不负责**: 选择图表类型、选择语言 (已在输入端指定)

---

### DataSpec编译 → 规范化

**职责**: 将Planner输出转为完整DataSpec

**核心操作**:
1. 查询`chart-library-mapping`表: `chart_type → {python_lib, frontend_lib}`
2. 根据`language`配置字体设置
3. 映射数据源: `indicator → FRED/AKShare series_code`
4. 推断数据形态: `Shape` (TS_1D/CS_1D/...)
5. 构建`llm_payload_policy`: 长时序降维,短时序保留原始

---

### 数据准备 → 真实数据

**职责**: 从数据源拉取数据并应用策略

**处理逻辑**:
```python
if shape == "TS_1D" and (点数 > 200 or 时间跨度 > 30天):
    给LLM: {
        "repr": 时序统计特征 (最值/拐点/区间),
        "recent_raw": 最近30天原始数据
    }
else:
    给LLM: 完整原始数据
```

---

### Coder LLM → 代码生成

**职责**: 生成指定库和语言的绘图代码

**输入**:
- DataFrame (真实数据)
- DataSpec (包含library和language配置)

**输出**:
- 可执行Python/JS代码
- 生成的图片 (带指定语言标签)

**语言处理**:
- `zh-CN`: 配置中文字体 (`Arial Unicode MS`, `SimHei`)
- `en-US`: 使用默认英文字体

---

### Narrator LLM → 总结生成

**职责**: 用指定语言撰写图表总结

**输入**:
- 图片
- DataSpec元信息
- 关键数值点 (避免LLM幻觉)
- (可选) 生成代码

**约束**:
- 所有数字必须引用提供的关键点
- 用指定language语言撰写
- 符合role的专业表述风格

---

## LLM数据暴露策略

### 时序数据 vs 横截面数据

| 数据类型 | 判断条件 | 给LLM的策略 |
|---------|---------|------------|
| **长时序** | 点数>200 或 跨度>30天 | 降维表征 + 最近30天原始 |
| **短时序** | 点数≤200 且 跨度≤30天 | 完整原始数据 |
| **横截面** | Shape=CS_* | 完整原始数据 (行数<500) |

**动机**:
- 长时序全给LLM易出错 (如一年股票日线数据)
- 降维后提供统计特征 + 部分原始数据平衡准确性

**降维方法** (可选):
- 简单统计特征 (最值/均值/拐点)
- Tsfresh时序特征提取
- TS2Vec深度学习表征

---

## 技术栈

### 数据源
- FRED: `pandas-datareader`
- AKShare: `akshare`
- 横截面: 直接HTTP请求

### 绘图库
- **Tier 1核心**: `matplotlib`, `mplfinance`
- **Tier 2高频**: `seaborn`, `plotly`
- **Tier 3-4**: `matplotlib`, `mplfinance`, `plotly`, `networkx`

**参考文档**: `library-installation.md`

### LLM调用
- Provider: OpenRouter/OpenAI/Anthropic
- 已集成的客户端: `src/chart_synth_v2/services/llm/`

---

## 输出结构

每个生成的图表包含:

```
output/20251117_143052_line_zh-CN_macro_a3f8b2d1/
├── chart.png              # 生成的图片
├── code.py                # 绘图代码
├── summary.txt            # 自然语言总结
├── dataspec.json          # 完整DataSpec
├── data.csv               # 使用的真实数据
└── metadata.json          # 元数据 (时间戳/状态/配置)
```

---

## 扩展阅读

- `chart-distribution-strategy.md` - 28种图表类型的分层分布
- `chart-library-mapping.md` - 图表类型到绘图库的映射表
- `library-installation.md` - Python绘图库安装指南
- `../test/data_sources_test/README.md` - 数据源详细说明
- `../src/chart_synth_v2/models/enums.py` - 主题/角色/任务枚举定义

---

**创建日期**: 2025-01-17
**维护者**: 合成图表项目组
