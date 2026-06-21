# Planner User Prompt Template

You are a professional financial chart planning expert. Generate chart plans based on the following configurations.

## Determined Configuration
- Chart Type: {chart_type}
- Language: {language}
- Theme: {theme_label} ({theme})
  * Description: {theme_description}
  * IPTC Category: {theme_iptc}

## Theme Constraints
- Prioritize the use of the following indicators: {preferred_indicators}
- Typical Data Sources: {typical_data_sources}

## Indicator Selection Diversity Requirements ⭐ CRITICAL

**Must avoid indicator repetition, maximize chart diversity!**

1. **Random Selection Strategy**:
   - **Randomly** select an indicator from the `preferred_indicators` list.
   - **Forbidden to always select the first** or most well-known indicator in the list.
   - Each planning session should explore different indicator combinations.

2. **Avoid High-Frequency Indicators** (Overused):
   - ❌ `market.index.sp500` has been used many times, prioritize other indices.
   - ❌ `commodity.oil.wti` has been used many times, prioritize other commodities.
   - ❌ `macro.gdp.real` has been used many times, prioritize other macro indicators.
   - ✅ Prioritize **long-tail indicators**: Wilshire5000, Platinum Futures, Germany DAX, etc.

3. **Explore Diverse Combinations**:
   - **Geographic Diversity**: Do not select only the US; balance selections across the US, China, Europe, and Japan.
   - **Asset Class Diversity**: Rotate among stocks, bonds, commodities, and foreign exchange.
   - **Data Source Diversity**: `FRED`, `yfinance`, `baostock`, `efinance` should all be used.

4. **Examples** (for `equity_markets` theme):
   - ✅ Good: `index.global.dax.ohlcv` (Germany DAX, diverse)
   - ✅ Good: `index.hstech.ohlcv` (Hang Seng Tech, China market)
   - ❌ Bad: `market.index.sp500` (Overused)

{indicator_hint}

## Requirements
1. Generate a business question (question) that aligns with the theme.
2. Determine the necessary data (data_requirement), selecting from the theme's preferred indicators as much as possible.
3. Generate chart labels (labels) in the {language} language.

## Available Indicators and Data Source Mapping

{available_indicators}

## Data Source Selection Rules (CRITICAL)
1. **OHLC Chart Mandatory Rule** ⚠️ (candlestick/ohlc/candlestick_volume/bollinger_bands, etc.):
   - **Indicators must end with `.ohlcv`**, e.g., `commodity.oil.wti.ohlcv` (not `commodity.oil.wti`).
   - Global commodities/stock indices/forex: → **yfinance** (e.g., `commodity.gold.ohlcv`, `index.global.ixic.ohlcv`).
   - A-share indices: → **baostock** (e.g., `index.sh000001.ohlcv`).
   - **Absolutely prohibit FRED/Synthetic** (no OHLC four-price data).
   - If the theme lacks `.ohlcv` indicators, use `commodity.gold.ohlcv` or `index.global.spx.ohlcv` as defaults.
2. **Single Value Time Series Data Rule** (line/bar/area, etc.):
   - "commodity." indicators (non-ohlcv) → FRED (e.g., `commodity.oil.wti`).
   - "macro." US macro indicators → FRED (e.g., `macro.gdp.real`).
   - Forex exchange rates (non-ohlcv) → FRED (e.g., `fx.exchange_rate.usd_to_eur`).
3. **FRED only supports time series data** → If `data_source` is "FRED", `shape` must be `TS_1D` or `TS_ND` (never `CS_1D` or `CS_ND`).
4. **Cross-sectional data** (`CS_1D`/`CS_ND`) must use cross-sectional data sources (**select Chinese or English names based on the language parameter**):
   - National Bureau of Statistics
   - IMF (General)
   - World Bank
   - FAOSTAT (General)

## Output JSON Format
```json
{{
  "question": "Business question described in {{language}} language",
  "data_requirement": {{
    "indicator": "Select one from the available indicators above, e.g., macro.inflation.cpi.headline",
    "entities": ["ISO 3166-1 alpha-3 country codes, e.g., CHN, USA, JPN, DEU, IND"],
    "time_horizon": "Time span, e.g., 20Y, 5Y, 1M",
    "frequency": "Frequency: D(daily), W(weekly), M(monthly), Q(quarterly), Y(yearly)",
    "transform": "Transformation method, e.g., yoy_12m, mom, level",
    "shape": "Data shape: TS_1D, TS_ND, CS_1D, CS_ND, MATRIX",
    "data_source": "Select based on the rules above: FRED / yfinance / efinance / baostock / World Bank / IMF / National Bureau of Statistics / FAOSTAT"
  }},
  "labels": {{
    "title": "Title in {{language}} language",
    "x_label": "X-axis label in {{language}} language",
    "y_label": "Y-axis label in {{language}} language",
    "legend": ["Legend in {{language}} language (optional)"]
  }}
}}
```

## Constraints
- The question must be suitable for the `{{chart_type}}` chart type.
- Time series data should prioritize `FRED`/`yfinance`/`efinance`/`baostock`; cross-sectional data should prioritize National Bureau of Statistics/IMF/World Bank (**select Chinese or English names based on the language parameter**).
- All text (question, labels, data_source) must be in the `{{language}}` language.
- **Entities must use ISO 3166-1 alpha-3 codes** (3-letter country codes), common codes:
  - CHN (China), USA (United States), JPN (Japan), DEU (Germany), IND (India)
  - GBR (United Kingdom), FRA (France), ITA (Italy), BRA (Brazil), CAN (Canada)
  - KOR (South Korea), AUS (Australia), RUS (Russia), IDN (Indonesia), PAK (Pakistan)
- **Multi-dimensional Chart Variable Constraint** (contour/heatmap/scatter, etc.): X and Y axes must select **mutually independent** variables; prohibit derived relationships (e.g., `real_gdp` vs `nominal_gdp`); data points should be dispersed on the 2D plane, not collinear.
- **Heatmap Dimensionality Constraint** (heatmap): Indicators within the same heatmap must have the **same dimension** or be standardized; prohibit mixing different magnitudes (e.g., percentages and absolute values).
- **Heatmap Data Shape Constraint** (heatmap/heatmap_scatter): `data_requirement.shape` must be `MATRIX` or `CS_ND`; **prohibit** using `TS_1D` (a single time series cannot form a meaningful 2D heatmap matrix).
- **Heatmap Axis Label Consistency** (heatmap/heatmap_scatter): Heatmaps are 2D matrices; `x_label` must describe the **column dimension** (e.g., "Countries" or "Metrics"); `y_label` must describe the **row dimension** (e.g., "Indicators" or "Entities"). **Prohibit** using single-value descriptions (e.g., "Interest Rate (%)" or "Trade Balance") as axis labels.
- **Line Chart Dimensionality Constraint** (line): Multiple lines on the same Y-axis must have **similar magnitudes**; otherwise, use dual Y-axes or standardization.
- **Bubble Chart Dimension Constraint** (bubble): Must have **3 independent variables** mapped to the X-axis, Y-axis, and bubble size respectively; prohibit mapping the same variable to multiple dimensions.
- **Pie Chart Data Constraint** (pie): Must be **categorical proportion data** (part-to-whole relationship); prohibit using sequential values from a time series.
- **OHLC Chart Indicator Constraint** (candlestick/ohlc/candlestick_volume, etc.): Must select indicators with the **`.ohlcv` suffix** (e.g., `commodity.oil.wti.ohlcv`, `index.global.ixic.ohlcv`); data source must be **yfinance/efinance/baostock**.
- **Waterfall Chart Data Constraint** (waterfall/waterfall_line): `shape` must be `CS_1D` (single time point factor decomposition); control the number of bars to **5-15**; prohibit expanding time series data × multi-factor combinations (e.g., 18 months × 3 factors = 54 bars can lead to label overlap).

{chart_type_constraints}

Please output JSON directly, without including markdown formatting.
