# FCPO 实验完整复盘（V2/V3 总结）

**创建日期**：2026-03-29
**目的**：完整记录 FCPO（Fact-Calibrated Preference Optimization）从假设到失败的全过程，为 V4 实验提供决策依据。

---

## 一、实验假设

### 1.1 核心 Insight

DPO 训练数据中 72% 的图表是代码合成的，保留了完整源数据（raw.csv / data_summary.txt）。可以用源数据做**确定性事实验证**，将奖励信号分解为确定性部分和概率性部分：

$$r(x,y) = r_{\text{fact}}(x,y) + r_{\text{quality}}(x,y)$$

### 1.2 FCPO Loss

在 DPO sigmoid loss 中注入 per-sample fact-calibrated margin：

$$L_i = -\log \sigma(\beta \cdot \Delta\text{logits}_i - \gamma \cdot \Delta r_{\text{fact},i})$$

- `Δr_fact > 0`：chosen 事实更准确 → 增大 margin → 加强偏好学习
- `Δr_fact < 0`：rejected 事实更准确 → 减小/反转 margin → 削弱偏好学习
- `Δr_fact = 0`：无 fact 信号（Tier 3 不可验证数据）→ 退化为标准 DPO

### 1.3 对比方法

| 方法 | 描述 | 信号使用方式 |
|------|------|------------|
| **FCPO** | 连续 margin: γ × Δr_fact | 加在 DPO logits 上 |
| **FDPO** | 二元翻转: Δr_fact < 0 时交换 chosen/rejected | 改数据 |
| **E-shuf** | 随机打乱 Δr_fact 分配 | 因果性对照 |
| **Weight mode** | margin 作为 logits 的乘数而非减数 | 缩放偏好 |

---

## 二、训练数据

### 2.1 原始偏好对：1700 条

| Tier | 数量 | 占比 | 来源 | 可验证性 |
|------|------|------|------|---------|
| Tier 1 (完全可验证) | 832 | 48.9% | V4 (raw.csv) + V3 含原始数据 | 任意数值、极值、趋势 |
| Tier 2 (部分可验证) | 390 | 22.9% | V3 仅统计摘要 | 极值、均值、趋势方向 |
| Tier 3 (不可验证) | 478 | 28.1% | fin-chart + finmme | 无源数据，margin=0 |

### 2.2 r_fact 构建 Pipeline（6 步）

```
Step 1: build_source_mapping.py → source_mapping.json (1700 条)
        图片文件名 → 源数据路径 + Tier 分类

Step 2: T0.3 Fact Extraction (gemini-2.5-flash-lite)
        chosen/rejected response → 提取事实声明 → 对照源数据验证
        → fact_scores.json (1189 条有效)

Step 3: compute_r_fact.py → r_fact.json (1700 条)
        r_fact = fact_precision = verifiable_correct / total_verifiable_claims
        delta_r_fact = r_fact_chosen - r_fact_rejected
        Tier 3: delta_r_fact = 0

Step 4: compute_r_quality.py → r_quality.json (1700 条)
        Judge 评估（排除 faithfulness 维度，避免与 r_fact 重叠）
        权重: completeness 46.2% + analysis 38.5% + conciseness 15.4%

Step 5: prepare_decomposed_data.py → dpo_decomposed_base.json
        自适应 α: α_i = 0.5 × min(claim_count/10, 1.0) × tier_factor
        tier_factor: Tier 1 = 1.0, Tier 2 = 0.6, Tier 3 = 0.0
        raw_margin = α × Δr_fact + (1-α) × Δr_quality

Step 6: generate_fcpo_data.py → 各实验变体 JSONL
        γ = 0.3 × mean_dpo_margins / mean_|Δr_fact|
          = 0.3 × 4.113 / 0.1451 = 8.5
```

### 2.3 r_fact 信号质量（致命弱点）

| 指标 | 值 | 含义 |
|------|-----|------|
| 有 fact 信号的样本 | ~72% (Tier 1+2) | 28% 完全无信号 |
| Δr_fact > 0 (chosen 更准) | ~28% | 仅 1/4 样本有正向信号 |
| Δr_fact = 0 (持平) | ~42% | 近半数无差异 |
| Δr_fact < 0 (rejected 更准) | ~19% | |
| mean \|Δr_fact\| | 0.1451 | 差异极小 |
| **SNR (信噪比)** | **~0.03** | **97% 噪声** |
| Δr_fact 与 Δr_quality Pearson 相关 | 0.13-0.39 | 两种信号弱相关 |
| 三种 fact 方法 Spearman 相关 | 0.13-0.39 | fact verification 本身不稳定 |

**核心问题**：大多数 chosen/rejected 对的事实准确性差异极小，信号被大量 Δ≈0 的样本淹没。

---

## 三、训练过程

### 3.1 两套训练框架

| 框架 | 平台 | 实现方式 | 推理 | 可靠性 |
|------|------|---------|------|--------|
| **ms-swift 4.0.2** | pku-246/247/248/14/H20 | monkey-patch DPOTrainer | SGLang | ❌ **mode collapse**，E0=0.630 |
| **LlamaFactory 0.9.5** | pku-248/H20 | 修改 5 个源文件 | transformers | ✅ E0=0.755，结果可信 |

**关键发现**：ms-swift + SGLang 推理存在系统性 mode collapse 问题。同一数据同一训练，ms-swift 推理 0.630 vs LlamaFactory 推理 0.755。**所有 ms-swift FCPO 结果不可信。**

### 3.2 ms-swift FCPO 实验结果（V2 项目，β=0.05，不可靠）

| 实验 | Judge | vs E0 | 方法 |
|------|-------|-------|------|
| **E1b (不钳位 γ=8.5)** | 0.660 | +0.030 | additive unclamped |
| E0-control | 0.630 | baseline | standard DPO |
| E-shuf | 0.612 | -0.018 | shuffle control |
| E1d (Tier1/2) | 0.611 | -0.019 | clamped, Tier1/2 only |
| E1a (钳位 γ=8.5) | 0.600 | -0.030 | additive clamped |
| E-fdpo | 0.593 | -0.037 | binary flip |
| E1c (weight) | 0.565 | -0.065 | multiplicative |

> ⚠️ E0=0.630 vs LF 的 0.755 证明这些结果受推理 bug 影响，相对排序可能也不可靠。

### 3.3 LlamaFactory FCPO 实验结果

#### V3 项目（H20, β=0.1, r_fact v1/v2, L2=200 样本）

| 排名 | 实验 | L2 Score | vs LF-2 | 备注 |
|------|------|---------|---------|------|
| 1 | FDPO-v2 | 0.764 | +0.009 | ⚠️ 数据 bug: 未真正实现 flip |
| 2 | FDPO-real-g4 | 0.762 | +0.007 | |
| 3 | FCPO-v2g4 | 0.762 | +0.007 | == FDPO-v2 数据 |
| 4 | FCPO-v1g2 | 0.756 | +0.001 | |
| 5 | **Shuffle-v2** | **0.756** | **+0.001** | ⚠️ 随机 margin 效果相同 |
| 6 | LF-2 (baseline) | 0.755 | — | 标准 DPO |
| 7 | FCPO-v1g1 | 0.753 | -0.002 | |
| 8 | FCPO-v2g1 | 0.752 | -0.003 | |
| 9 | FCPO-v2g2 | 0.750 | -0.005 | |
| 10 | FCPO-v1g4 | 0.744 | -0.011 | γ 过大有害 |

#### V2→LF 复现（pku-248, β=0.1, γ=8.5 不钳位, L2=200 样本）

| 实验 | Judge | vs SFT |
|------|-------|--------|
| LF-2 (standard DPO) | 0.755 | +0.011 |
| SFT baseline | 0.744 | — |
| lf_fcpo_ga16 | 0.729 | -0.015 |
| lf_fcpo_e1b | 0.727 | -0.017 |
| lf_fcpo_2epoch | 0.725 | -0.019 |
| lf_fcpo_beta005 | 0.718 | -0.026 |

---

## 四、评估过程

| 级别 | 样本量 | 用时 | 用途 | 可靠性 |
|------|--------|------|------|--------|
| L1 | — | 0 | 训练指标初筛 | 仅排除明显失败 |
| **L2** | **200** | ~30min | 主力筛选 | ±1-2% 波动，不足以区分 <1% 差异 |
| L3 | 1000 | ~2-3h | 论文最终 | 未对 FCPO 执行 |
| L4 | 50-100 | — | 人工评估 | 未执行 |

**评估配置固定**：
- Judge: gemini-2.5-flash-lite, temperature=0
- 维度: Faithfulness 35% + Completeness 30% + Analysis 25% + Conciseness 10%
- 推理: greedy decoding, max_tokens=2048

**问题**：几乎所有 FCPO 结论基于 L2 (200 样本)，200 样本的 ±1-2% 波动足以掩盖 FCPO 的微小差异。未做 L3 验证，未做多 seed 统计检验。

---

## 五、试验设计缺陷

| 缺陷 | 影响 |
|------|------|
| ms-swift 推理 mode collapse 未及时发现 | 大量实验结论错误（E1b "有效" 是假象） |
| L2 样本量不足 | 200 样本的 CI > 实验间差异 |
| FDPO-v2 数据 bug | flip 从未实现，FDPO-v2 == FCPO-v2g4 |
| 未跑多 seed | 无法区分真实提升 vs 随机波动 |
| γ 依赖特定实验 | γ=8.5 基于 R1-03 的 mean_margins=4.113 |
| r_fact 方法不稳定 | 三种 fact 评估方法互相关 0.13-0.39 |

---

## 六、结论：FCPO 为什么不 work

| 根因 | 证据 |
|------|------|
| **r_fact 信号太弱** | SNR=0.03, mean\|Δ\|=0.145, 42% 样本 Δ=0 |
| **fact 方法本身不稳定** | 三种方法 Spearman 0.13-0.39 |
| **Shuffle ≈ FCPO** | Shuffle=0.756 vs FCPO-v1g2=0.756（无因果效应） |
| **LF 实验全部低于 DPO** | 4 个 LF-FCPO: 0.718-0.729 < SFT 0.744 < DPO 0.755 |
| **大 γ 放大错误信号** | FCPO-v1g4=0.744（γ=4 最差） |
| **偏好对质量差异本身微小** | chosen/rejected 都是 SFT 模型生成，质量差异有限 |

---

## 七、论文中 0.764 分数的溯源

论文 Table 4 中的 FCPO 0.764 来自 `FDPO-v2`：
- **评估集**：L2 (200 样本) ，非 L3 (1000 样本)
- **数据 bug**：FDPO-v2 数据 == FCPO-v2g4 数据（flip 未实现）
- **真实 L3 分数**：未跑，但 V3 全部实验在 L2 上的最大提升仅 +0.009
- **不可在论文中使用此分数**

---

## 八、可供 V4 参考的优化方向

### A. 改进 r_fact 信号质量（根源问题）

| 方案 | 做法 | 预期 | 成本 |
|------|------|------|------|
| A1. 更强 LLM 提取 | GPT-4o/Claude 做 fact extraction | 更准确的 claims | 1700×2 条 API |
| A2. 多 Judge 投票 | 3 个 LLM 独立提取+验证 | 减少随机性 | 3x API |
| A3. 高信号过滤 | 只用 \|Δr_fact\| > 阈值的样本做 FCPO | 减少噪声 | 低 |
| A4. 规则提取数值 claims | 正则匹配数字 → 对照 raw.csv | 确定性验证 | 中 |

### B. 改进 margin 注入方式

| 方案 | 做法 |
|------|------|
| B1. 自适应 γ per tier | Tier 1 大 γ, Tier 2 小 γ, Tier 3=0 |
| B2. Sample weight 而非 margin | `weight = 1 + λ × |Δr_fact|` |
| B3. 二阶段训练 | Stage 1 标准 DPO → Stage 2 FCPO 高信号子集 |
| B4. SimPO + per-sample margin | 不需要 ref model，per-sample γ |

### C. 改变策略

| 方案 | 做法 |
|------|------|
| C1. Best-of-N + Fact reranking | 推理时用 r_fact rerank（不改训练） |
| C2. Fact-guided data selection | 用 r_fact 筛选高质量偏好对做标准 DPO |
| C3. DPO 数据扩增 | 1700 → 3000+，更多偏好对 |
| C4. 负面结果论文 | 详细分析 FCPO 为什么不 work |

---

## 九、关键文件索引

### V2 项目 (`$DATA_ROOT/dpo-v2/`)

| 文件 | 说明 |
|------|------|
| `scripts/compute_r_fact.py` | r_fact 计算 |
| `scripts/compute_r_quality.py` | r_quality 计算 |
| `scripts/prepare_decomposed_data.py` | 合并 + 自适应 α |
| `scripts/generate_fcpo_data.py` | 生成实验变体 |
| `scripts/patches/deploy_dpo_margin.py` | TRL per-sample margin 补丁 |
| `data/fcpo_gamma_config.json` | γ=8.5 配置 |
| `data/r_fact.json` | 1700 条 r_fact 数据 |
| `data/r_quality.json` | 1700 条 r_quality 数据 |
| `data/dpo_decomposed_base.json` | 合并后的分解数据 |
| `experiments/fcpo-interim-analysis.md` | ms-swift 中期分析（不可靠） |

### V3 项目 (`$DATA_ROOT/dpo-v3/`)

| 文件 | 说明 |
|------|------|
| `scripts/patch_fcpo.py` | LlamaFactory FCPO 4 文件补丁 |
| `scripts/generate_fcpo_data.py` | V3 版数据生成（γ=1/2/4） |
| `HANDOFF-2026-03-23.md` | 17 实验完整排名 |
| `results/FCPO-*.json` | 各实验 L2 评估结果 |

### 依赖项目

| 项目 | 路径 |
|------|------|
| DPO V1 | `$DATA_ROOT/dpo/` |
| SFT 项目 | `$DATA_ROOT/sft/` |
| 评估框架 | `$DATA_ROOT/benchmark/` |
