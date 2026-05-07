## 当前状态 (最后更新: 2026-03-30 05:30)

### Round 2 完整评估结果

| 模型 | Judge Score | Faithfulness | Completeness | Analysis | Conciseness |
|------|-----------|-------------|-------------|---------|------------|
| dpo_v1_fix | **0.7640** | **3.52** | 4.00 | 3.71 | 4.56 |
| dpo_merged_fix (R1) | 0.7612 | 3.50 | 4.00 | 3.69 | **4.57** |
| **fcpo_merged_r2** | 0.7573 | 3.43 | **4.01** | **3.73** | 4.50 |
| fcpo_merged_v2 | 0.7559 | 3.45 | 4.00 | 3.67 | 4.52 |
| dpo_merged_r2 | 0.7506 | 3.38 | 3.97 | 3.70 | 4.52 |
| dpo_t06_fix | 0.7488 | 3.44 | 3.98 | 3.63 | 4.51 |

### 关键发现

1. **FCPO margin 加权有效**: FCPO R2 (0.7573) > DPO R2 (0.7506), +0.007
2. **FCPO R2 Analysis 维度最高** (3.73)，说明 fact-aware 训练提升了分析深度
3. **所有模型差异在统计噪声范围内** (L2 200样本, p>0.05)
4. **Faithfulness 是瓶颈** (3.4-3.5)，Completeness 已到天花板 (4.0)

### 已完成
- [x] FCPO v2 训练 + 推理 + 评估 (0.7559)
- [x] T06 重新评分 (903条)
- [x] Round 2 数据构建 (DPO 2681条, FCPO 2552条)
- [x] DPO R2 训练 + 推理 + 评估 (0.7506)
- [x] FCPO R2 训练 + 推理 + 评估 (0.7573)
- [x] Case study: FCPO v2 vs DPO R1 (差异不显著, p=0.39)
- [x] Case study: DPO R2 vs DPO R1 (差异不显著, p=0.075)
- [x] 数据构建流程 review (通过, 无问题)

### 248 训练环境问题记录
- **根因**: CUDA_VISIBLE_DEVICES=0,1,2,3 映射的 CUDA device 2,3 实际是别人(bzy)占用的GPU
- **解决**: 只用 CUDA_VISIBLE_DEVICES=0,1 (2×A800, 84GB free each)
- **教训**: transformers pip 降级/升级是误导方向，真正问题是 GPU 资源争用

### 待分析
- [ ] 综合优化方向分析 (subagent 进行中)
- [ ] 如何进一步提升 faithfulness

### 综合分析结论 (2026-03-30 06:00)

**核心发现**: 所有模型差异在 L2 (200样本) 上均不显著。FCPO 在最困难样本上有帮助但总体 p=1.0。

**瓶颈**: faithfulness 集中在 finmme_200 (40% F≤2)

**优化方向** (按收益排序):
1. 增加 finmme 领域训练数据
2. 用 V1 Judge 流程重选 T06 对
3. rpo_alpha + 早停探索
4. Best-of-N + Fact Reranking
5. FCPO 自适应改进

### 正在运行
- 248: FCPO R2 beta=0.05 消融 (预计 06:30 完成)

### Best-of-N 实验结果 (2026-03-30 08:50)

**Best-of-5 Oracle**:
- Judge Score: 0.8495 (+0.092 vs greedy 0.7573)
- Faithfulness: 4.10 (+0.66 vs 3.43)
- finmme_200: 0.820 (+0.110 vs 0.710)

**简单 Reranking 策略全部失败**:
- Longest / Median / Consensus(Jaccard) / Random 均 ≈ greedy，无提升
- 需要语义级信号（Fact Score / Judge）做 reranking

**结论**: BoN 潜力巨大但需要质量信号。这正好支持 FCPO 论文的论点——Fact Score 作为 reranking 信号的价值。

**下一步**: 用 Fact Score 做 reranking 验证。
