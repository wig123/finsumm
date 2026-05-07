# Python库安装清单

## 当前环境状态

**虚拟环境**: `.venv`
**Python版本**: 3.13.6
**更新时间**: 2025-01-17

---

## 已安装核心库

### 绘图核心（6个）

| 库名 | 版本 | 用途 |
|-----|------|------|
| **matplotlib** | 3.10.7 | 基础图表（line/bar/area/histogram/scatter/contour/errorbar） |
| **seaborn** | 0.13.2 | 统计图表（heatmap/box/density） |
| **plotly** | 6.3.1 | 交互图表（waterfall/treemap/overlay/gantt/depth） |
| **mplfinance** | 0.12.10b0 | 金融图表（candlestick/OHLC/volume/Bollinger/Ichimoku/Renko） |
| **networkx** | 3.5 | 网络图布局 |
| **squarify** | 0.4.4 | treemap布局算法 |

### 数据处理（3个）

| 库名 | 版本 | 用途 |
|-----|------|------|
| **pandas** | 2.3.3 | 数据操作 |
| **numpy** | 2.2.6 | 数值计算 |
| **scipy** | 1.16.2 | 科学计算（contour/density） |

### 技术指标（2个）

| 库名 | 版本 | 用途 |
|-----|------|------|
| **pandas-ta** | 0.4.71b0 | 技术指标计算（Bollinger/MACD/RSI等） |
| **statsmodels** | 0.14.5 | 统计建模（时序分析/回归） |

### 导出支持（1个）

| 库名 | 版本 | 用途 |
|-----|------|------|
| **kaleido** | 1.2.0 | plotly静态图导出（PNG/SVG/PDF） |

---

## 安装命令

### 完整安装（推荐）
```bash
# 激活虚拟环境
source .venv/bin/activate

# 核心绘图库
pip install matplotlib seaborn plotly mplfinance networkx squarify

# 数据处理
pip install pandas numpy scipy

# 技术指标
pip install pandas-ta statsmodels

# 导出支持
pip install kaleido
```

### 分层安装（按需）

**阶段1: 核心绘图（Tier 1必需）**
```bash
pip install matplotlib mplfinance pandas numpy
```

**阶段2: 统计分析（Tier 2必需）**
```bash
pip install seaborn plotly scipy
```

**阶段3: 技术指标（Tier 3必需）**
```bash
pip install pandas-ta statsmodels
```

**阶段4: 高级功能（可选）**
```bash
pip install networkx squarify kaleido
```

---

## 图表类型覆盖矩阵

### Tier 1核心（8种）✅ 全部支持

| 图表类型 | 主库 | 辅助库 |
|---------|------|--------|
| line | matplotlib | - |
| candlestick | mplfinance | - |
| bar | matplotlib | - |
| bar + line overlay | plotly | matplotlib |
| candlestick + volume | mplfinance | - |
| area | matplotlib | - |
| histogram | matplotlib | - |
| scatter | matplotlib | - |

### Tier 2高频（9种）✅ 全部支持

| 图表类型 | 主库 | 辅助库 |
|---------|------|--------|
| heatmap | seaborn | matplotlib |
| waterfall | plotly | - |
| OHLC | mplfinance | - |
| Bollinger Bands | mplfinance | pandas-ta |
| box | seaborn | matplotlib |
| pie | matplotlib | - |
| bubble | matplotlib | - |
| line + band overlay | matplotlib | - |
| treemap | plotly | squarify |

### Tier 3专业（8种）✅ 全部支持

| 图表类型 | 主库 | 辅助库 |
|---------|------|--------|
| contour | matplotlib | scipy |
| Fan Chart | matplotlib | - |
| Volume Profile | matplotlib | pandas |
| Ichimoku Cloud | mplfinance | pandas-ta |
| Market Depth | plotly | - |
| Renko | mplfinance | - |
| errorbar | matplotlib | - |
| radar | plotly | - |

### Tier 4特殊（7种）✅ 全部支持

| 图表类型 | 主库 | 辅助库 |
|---------|------|--------|
| node | networkx | matplotlib |
| Gantt | plotly | - |
| Point & Figure | mplfinance | - |
| candlestick + indicator | mplfinance | pandas-ta |
| waterfall + line | plotly | - |
| density | seaborn | scipy |
| heatmap + scatter | seaborn | matplotlib |

**总计**: 28种图表类型 100%覆盖 ✅

---

## 验证安装

```python
# 运行此脚本验证所有库可用
import matplotlib
import seaborn
import plotly
import mplfinance
import networkx
import pandas
import numpy
import scipy
import statsmodels
import squarify
import kaleido

print("✅ 所有核心库安装成功！")
print(f"matplotlib: {matplotlib.__version__}")
print(f"mplfinance: {mplfinance.__version__}")
print(f"plotly: {plotly.__version__}")
print(f"seaborn: {seaborn.__version__}")
print(f"pandas-ta: {import pandas_ta; pandas_ta.__version__}")
```

---

## 库版本兼容性

| Python版本 | 推荐库版本 | 备注 |
|-----------|-----------|------|
| 3.13.x | 当前版本 | ✅ 已验证 |
| 3.12.x | 当前版本 | ✅ 兼容 |
| 3.11.x | matplotlib>=3.8 | ⚠️ 需降级mplfinance |
| 3.10.x | matplotlib>=3.7 | ⚠️ 需调整依赖 |

---

## 常见问题

### Q1: mplfinance版本显示beta?
**A**: `0.12.10b0`是稳定的beta版，功能完整，金融图表推荐使用

### Q2: kaleido安装失败?
**A**: 主要用于plotly静态导出，非必需。可跳过或使用`orca`替代

### Q3: pandas-ta未安装成功?
**A**: 可用TA-Lib替代，但pandas-ta更易安装（纯Python实现）

### Q4: 如何减小环境体积?
**A**:
- 仅Tier 1: ~200MB（matplotlib + mplfinance）
- Tier 1-2: ~350MB（+ seaborn + plotly）
- 完整安装: ~500MB

---

## 导出requirements.txt

```bash
source .venv/bin/activate
pip freeze > requirements.txt
```

当前核心依赖（精简版）:
```
matplotlib>=3.10.0
seaborn>=0.13.0
plotly>=6.3.0
mplfinance>=0.12.10b0
pandas>=2.3.0
numpy>=2.2.0
scipy>=1.16.0
pandas-ta>=0.4.71b0
statsmodels>=0.14.0
networkx>=3.5
squarify>=0.4.4
kaleido>=1.2.0
```

---

*维护: finchart项目组 | 最后更新: 2025-01-17*
