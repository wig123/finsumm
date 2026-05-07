# Fact 评分 Pipeline 对比与问题诊断

**创建日期**：2026-03-29

---

## 你的直觉（正确的逻辑）

```
源数据 (raw.csv / data_summary.txt)
    ↓
Judge 对照源数据，给 chosen/rejected 的事实准确性打分
    ↓
Δr_fact = r_fact_chosen - r_fact_rejected
```

**这个逻辑是对的。** 问题是：实际有 4 条不同的 pipeline，有的做对了，有的做错了。

---

## 四条 Pipeline 对比

### Pipeline ① `compute_r_quality.py`（❌ 完全错误）

```
chosen/rejected 文本 → gemini-flash-lite 评分（无图、无源数据）→ 1-5 分
```

| 问题 | 详情 |
|------|------|
| **不看源数据** | Judge 被告知"你看不到图表，不要因为数字可能错误而扣分" |
| **评的是写作水平** | 只看文本内部一致性和结构，不验证数据正确性 |
| **结果** | chosen=4.94, rejected=4.89（都接近满分，完全无区分度） |
| **影响** | FCPO 的 r_quality 成分 ≈ 0，公式退化为纯 r_fact |

### Pipeline ② `compute_r_fact.py` + `verify_facts.py`（⚠️ 逻辑对但噪声大）

```
Step 1: extract_source_facts.py
        raw.csv / data_summary.txt → 结构化 source_facts.json
        （规则提取：统计值、极值、趋势、时间范围）

Step 2: LLM 从 chosen/rejected 文本提取事实声明 (claims)
        "最高点在 2023-07 达到 8.5" → {type: extremum, value: 8.5, date: 2023-07}

Step 3: verify_facts.py 规则匹配
        claims vs source_facts，容差匹配（数值 ±3%/±5%/±15%）
        → fact_precision = verified / (verified + falsified)

Step 4: compute_r_fact.py
        delta_r_fact = fact_precision_chosen - fact_precision_rejected
```

| 优点 | 缺陷 |
|------|------|
| ✅ 有源数据对照 | ❌ claims 提取依赖 LLM，漏提/错提 |
| ✅ 规则验证确定性 | ❌ 只能验证数值/极值/趋势，不能验证复杂推理 |
| ✅ 无 LLM 评分噪声 | ❌ 1189/1700 有效（33 条提取失败，478 条 Tier3 无源数据） |
| | ❌ mean\|Δ\|=0.145，信号弱 |

### Pipeline ③ `compute_r_fact_llm.py` v1（⚠️ 逻辑对但区分度低）

```
source_facts.json + chosen文本 → gemini-flash-lite → 1-10 分
source_facts.json + rejected文本 → gemini-flash-lite → 1-10 分
delta = (chosen_score - rejected_score) / 10
```

| 优点 | 缺陷 |
|------|------|
| ✅ **有源数据对照** | ❌ 1-10 分太粗，42% 样本 delta=0 (tie) |
| ✅ 独立评分无 label leakage | ❌ flash-lite 模型偏弱 |
| ✅ 覆盖全部 Tier 1/2 | ❌ 正信号仅 39% |

### Pipeline ④ `compute_r_fact_llm_v2.py` v2（✅ 目前最好的）

```
source_facts.json + chosen文本 → gemini-3-flash → 1-100 分
source_facts.json + rejected文本 → gemini-3-flash → 1-100 分
delta = (chosen_score - rejected_score) / 100
```

| 优点 | 缺陷 |
|------|------|
| ✅ **有源数据对照** | ❌ v1/v2 方向一致性仅 47%（LLM 评分噪声大） |
| ✅ 1-100 细粒度，tie 降到 21% | ❌ 仍有 23% 负信号（delta<0） |
| ✅ 更强模型 (3-flash) | |
| ✅ 正信号 56% (Tier 1/2) | |

---

## 核心问题总结

| 问题 | 现状 |
|------|------|
| r_quality（Pipeline ①） | **完全无效**，不看源数据，评的是写作水平 |
| r_fact 规则版（Pipeline ②） | 逻辑对但 claims 提取是瓶颈，信号弱 |
| r_fact LLM v1（Pipeline ③） | 逻辑对但 1-10 分太粗 |
| r_fact LLM v2（Pipeline ④） | **目前最好**，但 LLM 评分本身有噪声（v1/v2 一致性 47%） |

**FCPO 的公式**：`raw_margin = α × Δr_fact + (1-α) × Δr_quality`
- 因为 Δr_quality ≈ 0，实际 = `α × Δr_fact`
- 而 α 本身又按 tier 衰减（Tier 2 × 0.6, Tier 3 = 0）
- 最终有效信号极少

---

## 正确的做法应该是什么

**你的直觉是对的**：应该拿源数据给 Judge，让它基于源数据给模型输出打分。Pipeline ④ 的逻辑是对的，但可以进一步改进：

### 改进方向

1. **多次评分取均值**：每个样本评 3 次，取均值，减少单次 LLM 噪声
2. **用更强的模型**：GPT-4o 或 Claude 做 fact checking（更贵但更准）
3. **给 Judge 看图片**：当前 Pipeline ④ 只给文本 + source_facts，不给图片。如果给图片，Judge 可以直接对照图表验证
4. **结合规则验证**：对数值 claims 用规则确定性验证（Pipeline ②），对非数值 claims 用 LLM 验证，两者互补
