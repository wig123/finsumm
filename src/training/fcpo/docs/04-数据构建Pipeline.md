# 偏好对构建 Pipeline（V4 标准流程）

**创建日期**：2026-03-29
**最后更新**：2026-03-29（确认方案 2 独立评分 + 图片 + 源数据）

---

## 〇、设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 评分方式 | **独立评分**（非对比） | FCPO 需要绝对分数；无 label leakage；避免位置偏差 |
| Judge 输入 | **图片 + 源数据 + 候选文本** | 图片验证视觉描述，源数据验证精确数值 |
| Judge 模型 | gemini-3-flash | 强于 flash-lite，与 V1 选对模型一致 |
| 训练格式 | 无 system prompt + 统一中文 prompt | 与 V1 DPO 和 SFT 训练格式一致 |

---

## 一、V1 vs T0.6 对比（为什么 V1 work 而 T0.6 不 work）

| | V1 原始 1700 ✅ | T0.6 新增 1115 ❌ |
|---|---|---|
| **Judge 模型** | gemini-3-flash (强) | gemini-2.5-flash-lite (弱) |
| **选对方式** | **对比选择**：6 候选 + GT + 图片一起给 Judge | **独立评分**：每个候选单独打分，取 max/min |
| **rejected 策略** | **Hard-negative**：刻意选"看起来专业但有事实错误"的 | 纯分数最低，无 hard-negative 概念 |
| **chosen faithfulness** | 4.94 (近满分) | 3.83 (远低于 V1 的 rejected) |
| **format** | 统一中文 prompt，无 system prompt | 英中混合 prompt，有 system prompt |
| **结果** | LF-2 = 0.755 | 合并后 0.745，拉低 1% |

**核心差异**：V1 用强 Judge 做对比选择 + hard-negative，T0.6 用弱 Judge 做独立评分。

---

## 二、V4 标准 Pipeline

### Step 1: 候选生成

**模型**：SFT checkpoint（exp-012/checkpoint-640, LoRA rank=256）
**每张图生成 6 个候选**：
- 候选 0：greedy decoding（do_sample=False）
- 候选 1-5：sampling（temperature=0.9, top_p=0.95, top_k=50）

```bash
# 服务器端执行（pku-246 或 H20）
python generate_candidates_single_gpu.py \
  --input data/images_to_process.json \
  --output data/candidates.json \
  --model /share4/yzy/models/qwen3-vl-8b-instruct \
  --adapter /share2/ww/qwen3vl-dpo/sft-checkpoint/exp-012-ckpt640 \
  --max-new-tokens 2048 \
  --num-samples 5 \
  --temperature 0.9 --top-p 0.95 --top-k 50
```

**输入格式**（每条需要 image 路径 + ground_truth）：
```json
{
  "index": 0,
  "image": "images/xxx.png",
  "messages": [...],
  "ground_truth": "参考标准摘要文本...",
  "_source": "V4"
}
```

### Step 2: 独立 Fact 评分（V4 新方案）

**脚本**：`qwen3vl-dpo-v4/scripts/score_candidates.py`
**Judge 模型**：`gemini-3-flash-preview-nothinking`
**方式**：每个候选**独立评分**——Judge 看到 1 个候选 + 源数据 JSON + 图片

```bash
python scripts/score_candidates.py \
  --candidates data/candidates.json \
  --source-facts ../qwen3vl-dpo-v2/data/source_facts.json \
  --image-base $DATA_ROOT/sft/data \
  --max-workers 8
```

**Judge 输入**：
- 图片（base64）— 验证视觉/结构描述
- 源数据（JSON）— 验证精确数值（如有）
- 候选文本 — 待评估

**Judge 输出**（每个候选独立）：
```json
{
  "score": 78,
  "errors": ["最高点日期写错，实际是 2024-03 非 2024-07"],
  "reasoning": "Most claims accurate but one significant date error"
}
```

### Step 3: 构建偏好对 + 格式转换

**脚本**：`qwen3vl-dpo-v4/scripts/build_dpo_pairs.py`

```bash
python scripts/build_dpo_pairs.py \
  --scores data/scored_candidates.json \
  --candidates data/candidates.json \
  --min-delta 5 \
  --output data/dpo_v4.json
```

**选对逻辑**：
- chosen = 6 个候选中 fact_score 最高的
- rejected = 6 个候选中 fact_score 最低的
- delta = chosen_score - rejected_score，低于阈值的跳过

**统一格式**（和 V1 DPO + SFT 训练一致）：
- **无 system prompt**
- **统一 user prompt**: `<image>\n请详细分析这张金融图表。`
- LlamaFactory sharegpt 格式

```json
{
  "conversations": [
    {"from": "human", "value": "<image>\n请详细分析这张金融图表。"}
  ],
  "chosen": {"from": "gpt", "value": "..."},
  "rejected": {"from": "gpt", "value": "..."},
  "images": ["images/xxx.png"]
}
```

**附带 _meta**（分析用，不参与训练）：
```json
{
  "_meta": {
    "chosen_score": 85,
    "rejected_score": 42,
    "delta": 43,
    "chosen_errors": [],
    "rejected_errors": ["最高点日期错误"],
    "has_source_facts": true
  }
}
```

---

## 三、数据源清单

### 可用图片池

| 来源 | 数量 | 有 Ground Truth | 有源数据(可验证) | 已用于 DPO |
|------|------|----------------|-----------------|-----------|
| V1 DPO 已用 | 1,700 | ✅ | 72% | ✅ 已用 |
| T0.6 已生成候选 | 1,280 | ✅ | 部分 | ⚠️ 已有候选，需重新选对 |
| SFT 剩余 | ~3,800 | ✅ | 部分 | ❌ 未用 |

### 扩增方案

**方案 A（快速）：重新选对 T0.6 的 1,280 张**
- 已有 6 个候选（`t06_candidates_1280.json`），不需要重新生成
- 只需要用 V1 的 Judge 流程（gemini-3-flash 对比选择）重新选对
- 预计：~1,100 条新偏好对，API 费用 1,280 次调用
- 时间：~2 小时（8 并发）

**方案 B（完整）：从 SFT 剩余 3,800 张生成**
- 需要先在 GPU 上生成候选（~6-12 小时 on 8×3090）
- 然后用 V1 Judge 流程选对
- 预计：~3,000 条新偏好对

**方案 C（A+B）：全部做**
- 总计可获得 ~4,000+ 条新偏好对
- 加上原始 1,700 = ~5,700 条

---

## 四、Fact-Guided 增强（可选，在 Step 2 后追加）

对 Step 2 选出的偏好对，用 r_fact v2（gemini-3-flash 1-100 评分）做二次验证：

1. 如果 r_fact 发现 chosen 事实错误多于 rejected → **翻转**（swap chosen/rejected）
2. 如果 |delta_r_fact| > 0.2 → 标记为高信号样本
3. 训练时可以只用高信号子集，或给高信号样本更高权重

**注意**：这一步是增强，不是替代。Step 2 的 Judge 对比选对是核心。

---

## 五、训练配置（固定，与 LF-2 一致）

| 参数 | 值 |
|------|-----|
| 框架 | LlamaFactory 0.9.5 |
| loss | sigmoid DPO |
| β | 0.1 |
| lr | 1e-5 |
| LoRA rank | 256 |
| epochs | 1 |
| batch_size | 8 |
| DeepSpeed | ZeRO-2 |
| SFT adapter | exp-012/checkpoint-640 |

---

## 六、关键文件索引

| 脚本 | 路径 | 用途 |
|------|------|------|
| 候选生成 | `qwen3vl-dpo/scripts/generate_candidates_single_gpu.py` | Step 1 |
| Judge 选对 | `qwen3vl-dpo/scripts/select_preference_pairs.py` | Step 2 |
| 格式转换 | `qwen3vl-dpo/scripts/convert_to_dpo_format.py` | Step 3 |
| T0.6 候选(已有) | `qwen3vl-dpo-v2/data/t06_candidates_1280.json` | 方案 A 的输入 |
