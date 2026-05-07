# Chart Synthesis Pipeline V3

基于双LLM协作的金融图表自动合成系统 - 从业务需求到Python代码图表的完整Pipeline

## 🎯 核心特性

- **五层Pipeline**: Planner (GPT-5) → DataSpec编译 → 数据获取 → Coder (Claude 4.5) → 编排
- **28种图表类型**: line, bar, scatter, candlestick, bollinger_bands 等 (分Tier 1-4)
- **10个金融主题**: macro_policy, inflation, commodities, equity_markets 等
- **4种可视化任务**: monitor, compare, explain, diagnose
- **真实数据源**: FRED (13接口), AKShare (11接口), 国家统计局, IMF, 世界银行, FAO
- **批量并发生成**: 支持ThreadPool/ProcessPool,最高4x加速
- **完整可重现**: 保存完整LLM trace (prompt/response/tokens)

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置LLM (已配置API易)
配置文件: `config/llm_config.yaml`
- Planner: GPT-5 (业务规划)
- Coder: Claude Sonnet 4.5 (代码生成)

### 3. 生成单个图表
```bash
# 使用批量配置
python scripts/run_batch.py --config batch_configs/demo.yaml

# 或使用Python API
python examples/simple_example.py
```

### 4. 批量生成
```bash
# 快速演示 (5个图表, ~2-3分钟)
python scripts/run_batch.py --config batch_configs/demo.yaml

# 多主题均衡 (20个图表, ~8-12分钟)
python scripts/run_batch.py --config batch_configs/multi_theme_balanced.yaml

# 横截面数据 (7个图表, 省份/国家对比)
python scripts/run_batch.py --config batch_configs/cross_sectional_demo.yaml
```

## 📁 项目结构

```
chart-synthesis-v3/
├── config/                      # 配置文件
│   ├── llm_config.yaml         # LLM API配置
│   ├── theme_mapping.yaml      # 10个金融主题
│   ├── task_mapping.yaml       # 4个可视化任务
│   ├── chart_library_mapping.yaml  # 28种图表类型
│   └── data_source_mapping.yaml    # 数据源映射
├── src/
│   ├── capabilities/           # 5层能力实现
│   │   ├── chart_planning/          # Layer 1: Planner LLM
│   │   ├── dataspec_compilation/    # Layer 2: DataSpec编译
│   │   ├── data_fetching/           # Layer 3: 数据获取
│   │   ├── chart_rendering/         # Layer 4: Coder LLM
│   │   └── pipeline_orchestration/  # Layer 5: 编排
│   ├── models/                 # 数据模型 (Pydantic)
│   └── utils/                  # 工具函数
├── batch_configs/              # 预定义批量配置
├── scripts/                    # 批量运行脚本
├── examples/                   # 示例代码
└── batch_output/               # 批量生成输出
```

## 📊 输出目录结构

每个生成的图表独立保存:

```
batch_output/demo/20251119_103746_candlestick_en-US_commodities_xxx/
├── artifacts/
│   ├── chart.png               # 生成的图表
│   └── code.py                 # 生成的Python代码
├── data/
│   ├── raw.csv                 # 原始数据 (CSV)
│   └── llm_payload.json        # 给LLM的数据策略
├── prompts/
│   ├── planner_input.json      # Planner输入
│   ├── planner_output.json     # Planner输出
│   ├── planner_llm_trace.json  # ✅ 完整LLM调用记录 (含prompt/response/tokens)
│   ├── coder_input.json        # Coder输入
│   ├── coder_output.json       # Coder输出
│   └── coder_llm_trace.json    # ✅ 完整LLM调用记录
├── logs/
│   └── retry_history.json      # 重试历史
├── dataspec.json               # 完整DataSpec
└── metadata.json               # 元数据 (状态/时间/token使用)
```

## 🔧 Python API 使用

```python
from src.models.planner_models import PlannerInput
from src.capabilities.pipeline_orchestration import ChartSynthesisPipeline

# 创建输入
planner_input = PlannerInput(
    chart_type="candlestick",   # 28种图表类型之一
    language="zh-CN",            # zh-CN / en-US
    theme="commodities",         # 10个金融主题之一
    task="monitor"               # 4个可视化任务之一
)

# 运行Pipeline
pipeline = ChartSynthesisPipeline()
result = pipeline.run(planner_input)

print(f"图表ID: {result['chart_id']}")
print(f"输出目录: {result['output_dir']}")
print(f"状态: {result['status']}")
```

### 可用的主题 (Theme)

| 代码 | 标签 | 优先指标示例 |
|------|------|--------------|
| `macro_policy` | 宏观政策 | fed.funds.rate, gdp.real |
| `inflation` | 通胀与价格 | cpi.headline, pce.core |
| `growth_employment` | 增长与就业 | gdp.real, unemployment.rate |
| `commodities` | 大宗商品 | oil.wti, gas.price |
| `equity_markets` | 权益市场 | stock indices |
| `fixed_income` | 固定收益 | 10y.treasury |
| `fx_trade` | 外汇与贸易 | exchange rates |
| `banking_credit` | 银行与信贷 | credit growth |
| `corporate_finance` | 企业财务 | earnings, cash flow |
| `real_estate` | 房地产 | house.price.index |

详见 `config/theme_mapping.yaml`

### 可用的任务 (Task)

| 代码 | 标签 | 描述 | 典型数据形态 |
|------|------|------|--------------|
| `monitor` | 监测 | 追踪趋势、拐点、最新状态 | TS_1D |
| `compare` | 比较 | 对比不同实体/时期/指标 | CS_1D, TS_ND |
| `explain` | 解释 | 叙述数据故事、事件影响 | TS_1D |
| `diagnose` | 诊断 | 识别异常、归因分析 | TS_ND, CS_ND |

详见 `config/task_mapping.yaml`

## 📈 批量配置文件

位于 `batch_configs/` 目录:

- **demo.yaml**: 快速演示 (5个图表, ~2-3分钟)
- **inflation_analysis.yaml**: 通胀主题深度分析 (8个图表)
- **cross_sectional_demo.yaml**: 横截面数据示例 (7个图表)
- **multi_theme_balanced.yaml**: 多主题均衡分布 (20个图表)

### 配置文件格式

```yaml
batch_name: "demo"
output_base_dir: "./batch_output"

execution:
  parallel: true            # 是否并行
  max_workers: 4            # 并发数
  use_process_pool: false   # 线程池 vs 进程池

charts:
  - chart_type: line
    language: zh-CN
    theme: inflation
    task: monitor
```

## 🔄 重试机制

- **LLM解析失败**: 最多3次重试,附带错误信息
- **代码执行失败**: 最多3次重试,附带错误堆栈
- **数据获取失败**: 最多3次重试

## 📖 核心概念

### DataSpec 六维正交结构

```python
dataspec = DataSpec(
    shape="TS_1D",              # 数据形态: TS_1D, CS_1D, TS_ND, CS_ND
    what={                       # 指标定义
        "indicator_id": "commodity.oil.wti",
        "data_source": "FRED",
        "series_code": "DCOILWTICO"
    },
    where={                      # 实体范围
        "entity_type": "country",
        "entities": ["US"]
    },
    when={                       # 时间维度
        "range": {"type": "relative", "lookback": "5Y"},
        "frequency": "W"
    },
    how={                        # 数据变换
        "transform": ["level"],
        "unit": "value"
    },
    language_config={...},       # 语言配置
    library_config={...},        # 绘图库配置
    output={                     # 输出配置
        "style_intent": "..."   # 样式意图描述
    }
)
```

### 灵活绘制模式 (v0.3.0)

- **核心理念**: 通过 `style_intent` 详细描述可视化意图,由Coder自主决策具体实现
- **优势**: 避免过度标注,根据数据特征智能选择可视化元素
- **示例**:
  ```
  "style_intent": "Professional commodities research narrative.
  Highlight major turning points with concise annotations tied to
  known market events. Show immediate market reaction by emphasizing
  price action in the 4–8 weeks after each annotated event..."
  ```

## ⚙️ 配置说明

### LLM配置
```yaml
# config/llm_config.yaml
pipeline_models:
  planner:
    provider: "apiyi"
    model: "gpt-5"              # 业务规划
    temperature: 0.7
    max_tokens: 8000

  coder:
    provider: "apiyi"
    model: "claude-sonnet-4-5-20250929"  # 代码生成
    temperature: 0.3
    max_tokens: 4000
```

### 数据源
- **FRED**: 13个美国经济时序指标
- **AKShare**: 11个中国市场数据接口
- **国家统计局**: 省级GDP、省级人口 (横截面)
- **IMF**: 全球通胀率、GDP增长率 (横截面)
- **世界银行**: 全球GDP、全球人口 (横截面)
- **FAO**: 中国农作物产量 (横截面)

## 📝 版本历史

### v0.3.0 (2025-11-18) - 当前版本
**灵活绘制模式 + 完整可重现性**
- ✅ 移除强制标注约束,改为模型自主决策模式
- ✅ 增强 `style_intent` 作为可视化意图传递的核心桥梁
- ✅ Planner/Coder 提示词优化,新增设计原则和评判标准
- ✅ **新增完整LLM trace记录**: `planner_llm_trace.json`, `coder_llm_trace.json`
  - 包含完整 prompt、response、token usage
  - 支持完全可重现的调试和分析

### v0.2.0 (2025-11-17)
**横截面数据 + 批量并发**
- ✅ 横截面数据源支持 (国家统计局、IMF、世界银行、FAO)
- ✅ 批量并发生成 (ThreadPool/ProcessPool,最高4x加速)
- ✅ 策略化批量生成 (balanced, tier-based, cross_sectional_only)

### v0.1.0 (2025-01-17)
**初始版本**
- ✅ 五层Pipeline架构
- ✅ 双LLM协作 (GPT-5 + Claude 4.5)
- ✅ 时序数据源 (FRED 13接口, AKShare 11接口)
- ✅ 28种图表类型映射
- ✅ 三级重试机制

## 🐛 已知限制

1. **图表库**: 当前主要支持matplotlib和mplfinance
2. **Narrator**: Layer 5总结生成层暂未实现
3. **数据源**: 所有API调用均为真实请求,网络异常时可能失败

## 📞 联系方式

- 项目仓库: [GitHub](https://github.com/your-repo)
- 问题反馈: GitHub Issues
- 许可证: MIT

---

**创建日期**: 2025-01-17
**最后更新**: 2025-11-19
**当前版本**: v0.3.0
