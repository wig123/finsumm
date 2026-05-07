# Chart Synthesis V3

金融图表-总结对的程序化合成系统，用于微调多模态大模型的图表理解能力。

## Goals & Non-goals

**Goals**:
- 生成高质量金融图表-总结对训练数据
- 通过代码+数据上下文降低总结错误率
- 支持28种图表类型、10个金融主题、中英双语

**Non-goals**:
- 不做实时数据展示系统
- 不做通用可视化工具（专注金融领域）

## Tech Stack

- **LLM**: GPT-5 (Planner) + Claude Sonnet 4.5 (Coder)
- **绘图**: matplotlib, mplfinance, plotly, ECharts, Highcharts
- **数据源**: FRED, AKShare, 国家统计局, IMF, 世界银行

## Directory Map

```
chart-synthesis-v3/
├── docs/                 # 文档体系
│   ├── _ai-rules.md      # AI写作规则（必读）
│   ├── decisions/        # ADR
│   └── features/         # 功能文档
├── config/               # 配置（LLM/主题/图表类型/数据源）
├── prompts/              # LLM提示词模板
├── src/capabilities/     # 五层Pipeline实现
│   ├── chart_planning/        # L1: Planner
│   ├── dataspec_compilation/  # L2: DataSpec编译
│   ├── data_fetching/         # L3: 数据获取
│   ├── chart_rendering/       # L4: Coder
│   └── pipeline_orchestration/# L5: 编排
├── batch_configs/        # 批量生成配置
├── scripts/              # 运行脚本
└── production_*/         # 生产数据集
```

## Architecture

**五层Pipeline**:
```
Planner LLM → DataSpec编译 → 数据获取 → Coder LLM → 编排输出
```

**核心设计**:
- DataSpec六维正交: shape × what × where × when × how × output
- 时间序列降维: >200点或>30天启用特征提取
- 真实金融风格: 极简标注，禁止装饰性元素

## Commands

```bash
# 单图表生成
python scripts/run_batch.py --config batch_configs/demo.yaml

# 批量生成（带进度监控）
python scripts/run_batch.py --config batch_configs/production_1000.yaml &
./monitor_progress.sh
```

## Rules for Claude

1. **写文档前**：必须先读 `docs/_ai-rules.md`
2. **新建功能**：**必须**使用 `./docs/_scripts/new.sh feat <name>`
3. **提示词修改**：
   - 可针对图表类型制定规则
   - **禁止**使用具体业务值（如CPI=3.2%）作为例子
4. **图表风格**：
   - 默认极简，禁止装饰性标注
   - 参考Bloomberg/FRED风格，非教学演示
5. **不确定时**：先分析（`--仅分析`），确认后再执行

## Task State

- `docs/features/<name>/spec.md` - 功能规格（稳定）
- `docs/features/<name>/state.md` - 进度跟踪（完成后删除）

重大决策同步到 `docs/decisions/*.adr.md`
