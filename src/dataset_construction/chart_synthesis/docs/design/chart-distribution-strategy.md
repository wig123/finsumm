# 金融图表数据集分布策略

## 核心原则

**分层不均衡分布** - 反映真实金融场景使用频率，保证核心类型充分训练，长尾类型有效覆盖

---

## 推荐分布（10,000张基准）

### Tier 1: 核心类型（60%, 6000张）

| 图表类型 | 占比 | 数量 |
|---------|------|------|
| line | 12% | 1,200 |
| candlestick | 10% | 1,000 |
| bar | 10% | 1,000 |
| bar + line overlay | 8% | 800 |
| candlestick + volume | 8% | 800 |
| area | 5% | 500 |
| histogram | 4% | 400 |
| scatter | 3% | 300 |

### Tier 2: 高频分析（25%, 2500张）

| 图表类型 | 占比 | 数量 |
|---------|------|------|
| heatmap | 5% | 500 |
| waterfall | 4% | 400 |
| OHLC | 3% | 300 |
| Bollinger Bands | 3% | 300 |
| box | 2.5% | 250 |
| pie | 2.5% | 250 |
| bubble | 2% | 200 |
| line + band overlay | 2% | 200 |
| treemap | 1% | 100 |

### Tier 3: 专业工具（10%, 1000张）

| 图表类型 | 占比 | 数量 |
|---------|------|------|
| contour | 2% | 200 |
| Fan Chart | 1.5% | 150 |
| Volume Profile | 1.5% | 150 |
| Ichimoku Cloud | 1.5% | 150 |
| Market Depth | 1% | 100 |
| Renko | 1% | 100 |
| errorbar | 0.8% | 80 |
| radar | 0.7% | 70 |

### Tier 4: 特殊场景（5%, 500张）

| 图表类型 | 占比 | 数量 |
|---------|------|------|
| node | 1.5% | 150 |
| Gantt | 1% | 100 |
| Point & Figure | 1% | 100 |
| candlestick + indicator | 0.8% | 80 |
| waterfall + line | 0.7% | 70 |
| density | 0.5% | 50 |
| heatmap + scatter | 0.5% | 50 |

---

## 完整类型清单（28种）

### 基础类型（15种）
line, bar, candlestick, OHLC, area, scatter, pie, histogram, box, bubble, heatmap, waterfall, contour, treemap, radar

### Overlay组合（7种）
bar + line, candlestick + volume, line + band (Bollinger), candlestick + indicator, waterfall + line, heatmap + scatter, Bollinger Bands

### 技术分析专用（4种）
Volume Profile, Ichimoku Cloud, Renko, Fan Chart

### 特殊场景（2种）
node (网络图), Gantt, Point & Figure, Market Depth, errorbar, density

---

## 关键约束

- **最小样本量**: 每类型 ≥70张（保证训练有效性）
- **核心集中**: Top 5类型占46%（line/candlestick/bar/overlay）
- **长尾覆盖**: 低频类型保留基础样本（避免零样本问题）

---

## 不同规模调整

| 数据集规模 | Tier1 | Tier2 | Tier3 | Tier4 | 最小样本/类 |
|-----------|-------|-------|-------|-------|------------|
| 5K | 70% | 20% | 7% | 3% | 30 |
| **10K** ⭐ | **60%** | **25%** | **10%** | **5%** | **70** |
| 50K | 50% | 30% | 15% | 5% | 500 |

---

## 移除的类型（vs ECD原29种）

**移除理由**: 金融场景使用频率<1%

- quiver (向量场) - 物理学用途
- 3d - 金融报告避免使用
- rose (玫瑰图) - 极少应用
- funnel (漏斗图) - 营销场景
- violin + box overlay - 过于复杂

---

## 新增类型（vs ECD原29种）

**新增基础类型（3种）**:
- Waterfall - 利润拆解、现金流分析
- OHLC - 欧美市场标准价格图
- Gantt - 项目时间表、IPO进度

**新增Overlay组合（3种）**:
- candlestick + volume - 交易软件标配
- candlestick + indicator - 技术分析（MA/EMA）
- waterfall + line - 现金流趋势

**新增技术分析工具（5种）**:
- Bollinger Bands - 波动率分析
- Volume Profile - 价格成交量分布
- Ichimoku Cloud - 一目均衡表
- Fan Chart - 风险情景分析
- Market Depth - 盘口可视化

**新增特殊类型（2种）**:
- Renko - 去噪价格图
- Point & Figure - 经典技术分析

---

## 验证方法

1. **真实采样对比**: 统计实际金融报告中的图表类型分布
2. **模型性能监控**: 核心类型准确率需>85%，长尾类型>60%
3. **A/B测试**: 对比60/25/10/5 vs 50/30/15/5方案

---

*更新时间: 2025-01*
