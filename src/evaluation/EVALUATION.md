# LLM 驱动的评估系统使用指南

## 概述

本评估系统使用 **Gemini 2.5 Flash** 作为核心评估引擎，结合传统指标（BLEU、ROUGE），对金融图表分析文本进行全面评估。

### 核心特性

- ✅ **LLM 驱动**: 使用 Gemini 2.5 Flash 进行智能评估，替代复杂的规则匹配
- ✅ **多模态支持**: 直接分析图表图片 + 文本，验证接地性
- ✅ **成本低廉**: 200 样本仅需 $0.4（约 2.8 元人民币）
- ✅ **代码精简**: 相比传统方法减少 70% 代码量
- ✅ **全面覆盖**: 13 个核心指标，覆盖所有评估维度

---

## 快速开始

### 1. 环境配置

#### 安装依赖

```bash
# 进入项目目录
cd $DATA_ROOT/benchmark

# 安装评估依赖
pip install -r requirements-eval.txt
```

#### 配置 API Key

```bash
# 设置 API易 的 API Key（用于 Gemini 2.5 Flash）
export OPENAI_API_KEY='your-api-key-here'

# 验证配置
echo $OPENAI_API_KEY
```

> **注意**: API易 使用 OpenAI 兼容的 API 格式，但调用的是 Gemini 模型。

---

### 2. 运行评估

#### 基础用法

```bash
# 评估 Qwen2.5-VL 的推理结果
python3 evaluate.py --results outputs/qwen25_results.jsonl

# 评估 Qwen3-VL 的推理结果
python3 evaluate.py --results outputs/qwen3_results.jsonl
```

#### 高级选项

```bash
# 限制评估样本数（用于快速测试）
python3 evaluate.py --results outputs/qwen25_results.jsonl --limit 10

# 跳过传统指标（仅使用 LLM 评估）
python3 evaluate.py --results outputs/qwen25_results.jsonl --skip-traditional

# 跳过图表接地评估（图片不可用时）
python3 evaluate.py --results outputs/qwen25_results.jsonl --skip-grounding

# 指定输出路径
python3 evaluate.py \
  --results outputs/qwen25_results.jsonl \
  --output outputs/qwen25_evaluation.json

# 使用 CPU（无 GPU 时）
python3 evaluate.py --results outputs/qwen25_results.jsonl --device cpu

# 计算 BERTScore（需要 GPU，较慢）
python3 evaluate.py --results outputs/qwen25_results.jsonl --use-bertscore
```

---

## 评估指标说明

### LLM 驱动的指标

#### 1. 数值准确性 (Numerical Accuracy)

使用 Gemini 提取文本中的数值，然后程序化计算差异。

**指标**:
- `numerical_f1`: 数值精确匹配 F1（容忍度 1%）
- `relaxed_accuracy`: 宽松匹配准确率（容忍度 5%）

**门槛**: `numerical_f1 >= 0.80`

#### 2. 图表接地性 (Chart Grounding)

使用 Gemini 的多模态能力，直接分析图表图片，验证文本是否忠实于图表内容。

**指标**:
- `parent_precision`: PARENT 风格的接地精度
- `grounding_score`: 整体接地分数（0-1）
- `hallucination_count`: 幻觉陈述数量

**门槛**: `parent_precision >= 0.85`

#### 3. 实体准确性 (Entity Accuracy)

使用 Gemini 提取金融实体（公司、日期、指标等），计算 F1 分数。

**指标**:
- `entity_f1`: 实体匹配 F1 分数
- `entity_precision`: 实体精度
- `entity_recall`: 实体召回率

**门槛**: `entity_f1 >= 0.90`

#### 4. 综合质量 (Comprehensive Quality)

使用 Gemini 进行 5 维度质量评分（类似 G-Eval）。

**维度**:
- `factual_accuracy` (30%): 事实准确性（1-5 分）
- `structure_adherence` (20%): 结构遵循性（1-5 分）
- `insight_depth` (25%): 洞察深度（1-5 分）
- `language_quality` (15%): 语言质量（1-5 分）
- `information_completeness` (10%): 信息封闭性（1-5 分）

**门槛**: `structure_adherence >= 4.5`

---

### 传统指标

#### 5. BLEU (SacreBLEU)

用于【数据关系】部分，评估精确匹配度。

**指标**:
- `bleu_1` ~ `bleu_4`: 1-4 gram BLEU 分数

#### 6. ROUGE

用于【核心洞察】部分，评估信息覆盖度。

**指标**:
- `rouge1`: Unigram 覆盖
- `rouge2`: Bigram 覆盖
- `rougeL`: 最长公共子序列

#### 7. BERTScore（可选）

语义相似度评估（需要 GPU）。

**指标**:
- `bertscore_f1`: 基于 BERT 的语义 F1 分数

---

## 评估结果解读

### 输出文件结构

```json
{
  "summary": {
    "numerical_f1": 0.87,
    "relaxed_accuracy": 0.92,
    "parent_precision": 0.88,
    "entity_f1": 0.91,
    "overall_quality": 4.2,
    "factual_accuracy": 4.5,
    "structure_adherence": 4.8,
    "insight_depth": 3.8,
    "passes_numerical_threshold": true,
    "passes_grounding_threshold": true,
    "passes_entity_threshold": true,
    "passes_structure_threshold": true
  },
  "traditional_metrics": {
    "overall": {
      "bleu_4": 0.42,
      "rouge1": 0.65,
      "rouge2": 0.48,
      "rougeL": 0.58
    },
    "section_数据关系": { ... },
    "section_核心洞察": { ... }
  },
  "per_sample_metrics": [ ... ]
}
```

### 门槛检查

系统会自动检查以下门槛：

| 指标 | 门槛 | 说明 |
|------|------|------|
| Numerical F1 | ≥ 0.80 | 数值错误率不超过 20% |
| PARENT Precision | ≥ 0.85 | 幻觉率不超过 15% |
| Entity F1 | ≥ 0.90 | 实体准确率不低于 90% |
| Structure Score | ≥ 4.5 | 结构完整性评分不低于 4.5/5.0 |

---

## 性能和成本

### 性能估算

- **单样本评估时间**: 约 2-3 秒（LLM 调用）
- **200 样本总时间**: 约 10-15 分钟（含传统指标）
- **传统指标时间**: 约 1-2 分钟（200 样本）

### 成本估算

#### Gemini 2.5 Flash（API易）

- **输入价格**: $0.075 / 1M tokens
- **输出价格**: $0.30 / 1M tokens

**200 样本评估成本**:
- 数值提取: 200 × 2 = 400 次调用
- 实体提取: 200 × 2 = 400 次调用
- 质量评估: 200 次调用
- 接地验证: 200 次调用（多模态）

**总计**: 约 $0.4（约 2.8 元人民币）

---

## 常见问题

### Q1: 如何跳过图表接地评估？

A: 使用 `--skip-grounding` 参数：

```bash
python3 evaluate.py --results outputs/qwen25_results.jsonl --skip-grounding
```

适用场景：图片文件不可用或路径不正确时。

### Q2: 评估速度太慢怎么办？

A: 可以采取以下措施：

1. **跳过传统指标**: `--skip-traditional`
2. **跳过 BERTScore**: 不使用 `--use-bertscore`
3. **限制样本数**: `--limit 50`（用于快速测试）

### Q3: API 调用失败怎么办？

A: 系统内置自动重试机制（最多 3 次），如果仍然失败：

1. 检查 API Key 是否正确
2. 检查网络连接
3. 查看错误信息，可能是速率限制

### Q4: 如何对比两个模型？

A: 分别评估后，对比 JSON 结果：

```bash
# 评估 Qwen2.5-VL
python3 evaluate.py \
  --results outputs/qwen25_results.jsonl \
  --output outputs/qwen25_eval.json

# 评估 Qwen3-VL
python3 evaluate.py \
  --results outputs/qwen3_results.jsonl \
  --output outputs/qwen3_eval.json

# 对比结果
python3 -c "
import json
qwen25 = json.load(open('outputs/qwen25_eval.json'))
qwen3 = json.load(open('outputs/qwen3_eval.json'))

print('Qwen2.5-VL:', qwen25['summary']['overall_quality'])
print('Qwen3-VL:', qwen3['summary']['overall_quality'])
"
```

---

## 技术架构

### 模块化设计

```
evaluators/
├── __init__.py                # 模块导出
├── gemini_client.py           # Gemini API 客户端
├── numerical_llm.py           # 数值准确性评估器
├── grounding_llm.py           # 图表接地评估器
├── quality_llm.py             # 综合质量评估器
├── entity_llm.py              # 实体准确性评估器
└── traditional.py             # 传统指标评估器
```

### 评估流程

```
加载推理结果 (JSONL)
    ↓
单样本评估 (并行 4 个评估器)
    ├─ 数值准确性评估
    ├─ 图表接地性评估
    ├─ 实体准确性评估
    └─ 综合质量评估
    ↓
传统指标评估 (BLEU、ROUGE)
    ↓
汇总统计 + 门槛检查
    ↓
保存结果 (JSON)
```

---

## 下一步

1. 等待推理完成
2. 拉取推理结果: `./gpu-pull.sh`
3. 运行评估: `python3 evaluate.py --results outputs/qwen25_results.jsonl`
4. 分析结果，对比 Qwen2.5-VL 和 Qwen3-VL 的性能

---

## 参考资料

- [Gemini API 文档](https://ai.google.dev/docs)
- [SacreBLEU](https://github.com/mjpost/sacrebleu)
- [ROUGE Score](https://github.com/google-research/google-research/tree/master/rouge)
- [BERTScore](https://github.com/Tiiiger/bert_score)
- [PARENT (Dhingra et al., 2019)](https://arxiv.org/abs/1906.01081)
- [G-Eval (Liu et al., 2023)](https://arxiv.org/abs/2303.16634)
