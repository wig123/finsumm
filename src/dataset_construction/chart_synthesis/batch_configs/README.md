# 批量配置文件说明

本目录包含预定义的批量生成配置文件,用于演示和快速开始。

## 配置文件列表

### 1. `demo.yaml` - 快速演示
- **用途**: 小规模测试,验证系统功能
- **图表数量**: 5个
- **特点**: 覆盖基本图表类型和主题,适合首次运行
- **执行时间**: ~2-3分钟 (并发)

```bash
# 预览
python scripts/run_batch.py --config batch_configs/demo.yaml --dry-run

# 执行
python scripts/run_batch.py --config batch_configs/demo.yaml
```

### 2. `inflation_analysis.yaml` - 通胀主题深度分析
- **用途**: 单一主题多维度可视化
- **图表数量**: 8个
- **特点**: 覆盖4种可视化任务 (monitor/compare/explain/diagnose)
- **执行时间**: ~3-5分钟 (并发)

```bash
python scripts/run_batch.py --config batch_configs/inflation_analysis.yaml
```

### 3. `cross_sectional_demo.yaml` - 横截面数据示例
- **用途**: 演示跨实体对比分析 (省份、国家)
- **图表数量**: 7个
- **特点**: 使用真实横截面数据源 (国家统计局、IMF、世界银行、FAO)
- **执行时间**: ~3-4分钟 (并发)

```bash
python scripts/run_batch.py --config batch_configs/cross_sectional_demo.yaml
```

### 4. `multi_theme_balanced.yaml` - 多主题均衡分布
- **用途**: 大规模批量生成,覆盖所有主要主题
- **图表数量**: 20个
- **特点**: 10个主题 × 2个任务,均衡分布
- **执行时间**: ~8-12分钟 (并发)

```bash
python scripts/run_batch.py --config batch_configs/multi_theme_balanced.yaml
```

## 配置文件结构

```yaml
# 批量名称 (用于输出目录命名)
batch_name: "your_batch_name"

# 输出根目录
output_base_dir: "./batch_output"

# 执行配置
execution:
  parallel: true           # 是否并行执行
  max_workers: 4           # 最大并发数 (建议2-8)
  use_process_pool: false  # 是否使用进程池 (默认线程池)

# 图表列表
charts:
  - chart_type: line       # 图表类型 (line/bar/scatter等)
    language: zh-CN        # 语言 (zh-CN/en-US)
    theme: inflation       # 主题 (见下方主题列表)
    task: monitor          # 任务 (monitor/compare/explain/diagnose)
    data_constraints: {}   # 数据约束 (可选)
```

## 支持的主题 (Theme)

1. `macro_policy` - 宏观政策
2. `inflation` - 通胀与价格
3. `growth_employment` - 增长与就业
4. `fx_trade` - 外汇与贸易
5. `equity_markets` - 权益市场
6. `fixed_income` - 固定收益
7. `commodities` - 大宗商品
8. `banking_credit` - 银行与信贷
9. `corporate_finance` - 企业财务
10. `real_estate` - 房地产

## 支持的任务 (Task)

1. `monitor` - 监控趋势
2. `compare` - 对比分析
3. `explain` - 解释关系
4. `diagnose` - 诊断异常

## 支持的图表类型

- `line` - 折线图
- `bar` - 柱状图
- `scatter` - 散点图
- `area` - 面积图
- `pie` - 饼图
- 等 (参考 `config/chart_library_mapping.yaml`)

## 输出目录结构

执行后会在 `output_base_dir/batch_name/` 目录下生成:

```
batch_output/
└── demo/
    ├── batch_summary.json              # 批量运行总结
    ├── line_zh-CN_inflation_20250117_120000/  # 单个图表目录
    │   ├── artifacts/
    │   │   ├── chart.png               # 生成的图表
    │   │   └── code.py                 # 生成的代码
    │   ├── data/
    │   │   ├── raw.csv                 # 原始数据
    │   │   └── llm_payload.json        # LLM数据策略
    │   ├── prompts/
    │   │   ├── planner_input.json
    │   │   ├── planner_output.json
    │   │   ├── coder_input.json
    │   │   └── coder_output.json
    │   ├── logs/
    │   │   └── retry_history.json
    │   └── metadata.json               # 图表元数据
    └── ...
```

## 高级用法

### 自定义数据约束

```yaml
charts:
  - chart_type: line
    language: zh-CN
    theme: inflation
    task: monitor
    data_constraints:
      preferred_indicators:
        - macro.inflation.cpi.headline
      time_range_hint: "recent_2y"
```

### 调整并发配置

```yaml
execution:
  parallel: true
  max_workers: 8              # 增加并发数
  use_process_pool: true      # 使用进程池(适合CPU密集任务)
```

## 常见问题

### Q: 如何选择 `max_workers`?
A: 建议根据CPU核心数和网络带宽设置:
- 本地运行: 2-4个worker
- 高性能服务器: 4-8个worker
- 网络限制较多: 降低到2-3个

### Q: 线程池 vs 进程池?
A:
- **线程池** (默认): 适合I/O密集任务 (API调用、LLM请求)
- **进程池**: 适合CPU密集任务 (大量数据处理、复杂计算)

### Q: 如何处理失败的图表?
A: 查看 `batch_summary.json` 中的 `results` 数组,失败项包含错误信息。可以提取失败项重新生成。

## 示例工作流

```bash
# 1. 预览配置
python scripts/run_batch.py --config batch_configs/demo.yaml --dry-run

# 2. 查看预览输出,确认无误后执行
python scripts/run_batch.py --config batch_configs/demo.yaml

# 3. 查看批量总结
cat batch_output/demo/batch_summary.json | jq .

# 4. 查看生成的图表
ls batch_output/demo/*/artifacts/chart.png
```

## 参考文档

- Pipeline原理: `../docs/chart-synthesis-pipeline.md`
- 项目状态: `../PROJECT_STATUS.md`
- 快速开始: `../QUICKSTART.md`
