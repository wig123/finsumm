# Planner User Prompt Template

你是一位专业的金融图表规划专家。根据以下配置生成图表规划。

## 已确定配置
- 图表类型: {chart_type}
- 语言: {language}
- 主题: {theme_label} ({theme})
  * 描述: {theme_description}
  * IPTC分类: {theme_iptc}

## 主题约束
- 优先使用以下指标: {preferred_indicators}
- 典型数据源: {typical_data_sources}

## 指标选择多样性要求 ⭐ CRITICAL

**必须避免指标重复，最大化图表多样性！**

1. **随机选择策略**：
   - 从 preferred_indicators 列表中**随机**选择一个指标
   - **禁止总是选择列表中的第一个**或最知名的指标
   - 每次规划都应探索不同的指标组合

2. **避免高频指标**（已被过度使用）：
   - ❌ market.index.sp500 已使用过多次，优先选择其他指数
   - ❌ commodity.oil.wti 已使用过多次，优先选择其他商品
   - ❌ macro.gdp.real 已使用过多次，优先选择其他宏观指标
   - ✅ 优先选择**长尾指标**：Wilshire5000、铂金期货、德国DAX等

3. **探索多样化组合**：
   - **地域多样性**：不要只选美国，均衡选择美国、中国、欧洲、日本
   - **资产类型多样性**：在股票、债券、商品、外汇中轮换
   - **数据源多样性**：FRED、yfinance、baostock、efinance 都应被使用

4. **示例**（equity_markets主题）：
   - ✅ 好：index.global.dax.ohlcv（德国DAX，多样化）
   - ✅ 好：index.hstech.ohlcv（恒生科技，中国市场）
   - ❌ 差：market.index.sp500（已被过度使用）

{indicator_hint}

## 要求
1. 生成一个符合主题的业务问题(question)
2. 确定需要什么数据(data_requirement),尽量从主题的优先指标列表中选择
3. 用{language}语言生成图表标签(labels)

## 可用指标与数据源映射

{available_indicators}

## 数据源选择规则 (CRITICAL)
1. **OHLC图表强制规则** ⚠️ (candlestick/ohlc/candlestick_volume/bollinger_bands等):
   - **指标必须以 `.ohlcv` 结尾**，如 commodity.oil.wti.ohlcv（不是 commodity.oil.wti）
   - 全球商品/股指/外汇: → **yfinance** (如 commodity.gold.ohlcv, index.global.ixic.ohlcv)
   - A股指数: → **baostock** (如 index.sh000001.ohlcv)
   - **绝对禁止 FRED/Synthetic**（无 OHLC 四价数据）
   - 如果主题没有 `.ohlcv` 指标，使用 commodity.gold.ohlcv 或 index.global.spx.ohlcv 作为默认
2. **单值时序数据规则** (line/bar/area等):
   - "commodity." 指标（非ohlcv） → FRED (如 commodity.oil.wti)
   - "macro." 美国宏观指标 → FRED (如 macro.gdp.real)
   - 外汇汇率（非ohlcv） → FRED (如 fx.exchange_rate.usd_to_eur)
3. **FRED 只支持时序数据** → 如果 data_source 是 "FRED"，shape 必须是 TS_1D 或 TS_ND（绝不能是 CS_1D 或 CS_ND）
4. **横截面数据** (CS_1D/CS_ND) 必须使用横截面数据源（**根据 language 参数选择中英文名称**）：
   - 国家统计局 / National Bureau of Statistics
   - IMF（通用）
   - 世界银行 / World Bank
   - FAOSTAT（通用）

## 输出JSON格式
```json
{{
  "question": "用{{language}}语言描述的业务问题",
  "data_requirement": {{
    "indicator": "从上述可用指标中选择一个,如macro.inflation.cpi.headline",
    "entities": ["ISO 3166-1 alpha-3 国家代码,如 CHN, USA, JPN, DEU, IND"],
    "time_horizon": "时间跨度,如20Y, 5Y, 1M",
    "frequency": "频率: D(日), W(周), M(月), Q(季), Y(年)",
    "transform": "变换方式,如yoy_12m, mom, level",
    "shape": "数据形态: TS_1D, TS_ND, CS_1D, CS_ND, MATRIX",
    "data_source": "根据上述规则选择: FRED / yfinance / efinance / baostock / 世界银行/World Bank / IMF / 国家统计局/National Bureau of Statistics / FAOSTAT"
  }},
  "labels": {{
    "title": "{{language}}语言的标题",
    "x_label": "{{language}}语言的X轴标签",
    "y_label": "{{language}}语言的Y轴标签",
    "legend": ["{{language}}语言的图例(可选)"]
  }}
}}
```

## 约束
- 问题必须符合`{{chart_type}}`图表类型的适用场景
- 时序数据优先使用FRED/yfinance/efinance/baostock，横截面对比优先使用国家统计局/IMF/世界银行（**根据language参数选择中英文名称**）
- 所有文本(question, labels, data_source)必须是`{{language}}`语言
- **entities 必须使用 ISO 3166-1 alpha-3 代码**（3字母国家代码），常用代码：
  - CHN(中国), USA(美国), JPN(日本), DEU(德国), IND(印度)
  - GBR(英国), FRA(法国), ITA(意大利), BRA(巴西), CAN(加拿大)
  - KOR(韩国), AUS(澳大利亚), RUS(俄罗斯), IDN(印尼), PAK(巴基斯坦)
- **多维图表变量约束** (contour/heatmap/scatter等): X和Y轴必须选择**相互独立**的变量，禁止派生关系（如 real_gdp vs nominal_gdp）；数据点需在二维平面分散分布，不能共线
- **热力图量纲约束** (heatmap): 同一热力图中的指标必须是**同一量纲**或经过标准化，禁止混合不同量级（如百分比与绝对值）
- **热力图数据形态约束** (heatmap/heatmap_scatter): data_requirement.shape 必须是 **MATRIX** 或 **CS_ND**，**禁止**使用 TS_1D（单一时间序列无法构建有意义的二维热力矩阵）
- **热力图轴标签一致性** (heatmap/heatmap_scatter): 热力图是二维矩阵，x_label 必须描述**列维度**（如 "Countries/国家" 或 "Metrics/指标"），y_label 必须描述**行维度**（如 "Indicators/指标" 或 "Entities/实体"）。**禁止**用单一值的描述（如 "Interest Rate (%)" 或 "Trade Balance"）作为轴标签
- **折线图量纲约束** (line): 同一Y轴的多条线必须是**相近量级**，否则需双Y轴或标准化
- **气泡图维度约束** (bubble): 必须有**3个独立变量**分别映射到X轴、Y轴和气泡大小，禁止用同一变量映射多个维度
- **饼图数据约束** (pie): 必须是**分类占比数据**（部分与整体关系），禁止用时间序列逐期值
- **OHLC图表指标约束** (candlestick/ohlc/candlestick_volume等): 必须选择带 **.ohlcv** 后缀的指标（如 commodity.oil.wti.ohlcv, index.global.ixic.ohlcv），数据源必须选择 **yfinance/efinance/baostock**
- **瀑布图数据约束** (waterfall/waterfall_line): shape 必须是 **CS_1D**（单时点因素分解），条形数控制在 **5-15个**；禁止将时序数据×多因素组合展开（如18个月×3因素=54条形会导致标签重叠）

{chart_type_constraints}

请直接输出JSON,不要包含markdown标记。
