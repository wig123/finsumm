# 推理参数配置说明

## 当前配置（选项C：纯贪婪解码）

### 脚本参数
```python
outputs = model.generate(
    **inputs,
    max_new_tokens=2048,
    do_sample=False  # 贪婪解码，确定性输出
)
```

### 配置原因

1. **任务需求**: 构建benchmark评估数据集
2. **可重现性**: 需要确定性输出，便于多次运行对比
3. **公平对比**: Qwen2.5-VL 和 Qwen3-VL 在相同条件下比较
4. **符合Ground Truth**: GPT-5生成的参考答案可能也使用确定性参数

---

## Qwen-VL官方推荐参数

### 方案对比

| 方案 | do_sample | temperature | top_p | top_k | 适用场景 |
|------|-----------|-------------|-------|-------|---------|
| **选项A: 官方推荐（采样模式）** | True | 0.7 | 0.8 | 20 | 生产环境、多样化输出 |
| **选项B: 低温采样** | True | 0.1 | 0.9 | 50 | 平衡确定性和多样性 |
| **选项C: 贪婪解码（当前）** | False | - | - | - | Benchmark、确定性评估 |

### 官方推荐配置

#### Instruct 模型（Qwen3-VL-8B-Instruct）
```python
outputs = model.generate(
    **inputs,
    max_new_tokens=2048,
    do_sample=True,
    temperature=0.7,
    top_p=0.8,
    top_k=20,
    repetition_penalty=1.0,
    presence_penalty=1.5
)
```

#### Thinking 模型（推理增强）
```python
outputs = model.generate(
    **inputs,
    max_new_tokens=4096,
    do_sample=True,
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    repetition_penalty=1.0,
    presence_penalty=0.0
)
```

---

## 参数详解

### 核心参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| **max_new_tokens** | int | 2048 | 最大生成token数 |
| **do_sample** | bool | False | 是否启用采样（False=贪婪解码） |
| **temperature** | float | 1.0 | 控制随机性（仅do_sample=True时有效） |
| **top_p** | float | 1.0 | 核采样阈值（累积概率） |
| **top_k** | int | 50 | Top-K采样（保留概率最高的K个token） |

### 高级参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| **repetition_penalty** | float | 1.0 | 重复惩罚（>1.0减少重复） |
| **presence_penalty** | float | 0.0 | 存在惩罚（鼓励新token） |
| **num_beams** | int | 1 | Beam search宽度（>1启用束搜索） |
| **early_stopping** | bool | False | 束搜索是否提前停止 |

---

## 参数影响分析

### temperature（温度）

```
temperature = 0.1  →  输出非常确定，接近贪婪解码
temperature = 0.7  →  平衡创造性和准确性（官方推荐）
temperature = 1.0  →  标准采样
temperature = 1.5  →  高度随机，可能产生不合理输出
```

**金融图表分析建议**: 0.6-0.8

### top_p（核采样）

```
top_p = 0.5   →  只考虑累积概率前50%的token
top_p = 0.8   →  官方推荐
top_p = 0.95  →  Thinking模型推荐
top_p = 1.0   →  考虑所有token
```

### top_k（Top-K采样）

```
top_k = 1     →  等同于贪婪解码
top_k = 20    →  官方推荐
top_k = 50    →  更多样化
top_k = 0     →  禁用Top-K
```

---

## 警告信息说明

### 常见警告

```
The following generation flags are not valid and may be ignored: ['temperature', 'top_p', 'top_k']
```

**原因**: Qwen3-VL的processor内部实现会默认添加这些参数，但当`do_sample=False`时这些参数无效。

**影响**: ✅ **无影响**。实际执行的是贪婪解码（`do_sample=False`优先级更高）。

**解决方案**:
1. 忽略警告（推荐）
2. 设置环境变量：`export TRANSFORMERS_VERBOSITY=error`

---

## 不同场景推荐配置

### Benchmark评估（当前使用）
```python
max_new_tokens=2048,
do_sample=False
```
✅ 确定性、可重现

### 生产环境
```python
max_new_tokens=2048,
do_sample=True,
temperature=0.7,
top_p=0.8,
top_k=20
```
✅ 平衡准确性和多样性

### 创意生成
```python
max_new_tokens=4096,
do_sample=True,
temperature=1.0,
top_p=0.95,
top_k=50
```
✅ 更多样化的输出

### 极度保守
```python
max_new_tokens=2048,
do_sample=True,
temperature=0.1,
top_p=0.9,
top_k=10
```
✅ 接近确定性但保留采样

---

## 参考资料

- [Qwen3-VL官方文档](https://github.com/QwenLM/Qwen3-VL)
- [Transformers Generation参数](https://huggingface.co/docs/transformers/main_classes/text_generation)
- [Context7 Qwen3-VL文档](https://context7.com/qwenlm/qwen3-vl)

---

## 修改历史

- **2025-11-17**: 初始配置（选项C：纯贪婪解码）
  - 移除 `temperature=0.7`（与`do_sample=False`冲突）
  - 仅保留 `max_new_tokens=2048, do_sample=False`
  - 理由：构建benchmark数据集，需要确定性输出
