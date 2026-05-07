# DPO V4 实验项目

## 项目定位

基于 V2/V3 FCPO 实验的教训，探索能够真正利用源数据可验证性的方法，为 ACMM 2026 论文提供实验支撑。

**你的第一步**：读完本文件后，依次读取：
1. `00-FCPO实验复盘.md` — V2/V3 完整教训
2. `01-实验计划.md` — V4 方案与优先级
3. `02-服务器资源.md` — SSH 连接、路径、GPU 状态
4. `03-API配置.md` — 所有 API key

然后检查当前状态（哪些任务已完成、服务器上什么在跑），确定下一步行动。

---

## 核心上下文

### 已确认事实

| 事实 | 数据 |
|------|------|
| SFT baseline (exp-012/ckpt-640) | L2=0.744 |
| 标准 DPO best (LF-2, β=0.1, rank=256) | L2=0.755 |
| FCPO 全部无效 | Shuffle ≈ FCPO，LF-FCPO < SFT |
| r_fact SNR=0.03 | 97% 噪声 |
| ms-swift 推理不可靠 | mode collapse |
| LlamaFactory 推理可靠 | ✅ |

### 基础模型与数据

- **基础模型**: Qwen3-VL-8B-Instruct (`/share4/yzy/models/qwen3-vl-8b-instruct`)
- **SFT checkpoint**: exp-012/checkpoint-640 (LoRA rank=256)
- **DPO 数据**: 1700 偏好对 (pku-246: `/home/ww/qwen3vl-dpo$DATA_ROOT/dpo/`)
- **图片**: 7677 张 (pku-246: `/home/ww/qwen3vl-dpo/data/images/`)
- **训练框架**: **LlamaFactory 0.9.5**（统一，不用 ms-swift）
- **评估**: FinMME-1000, Judge=gemini-2.5-flash-lite

### 前序项目

| 项目 | 路径 | 内容 |
|------|------|------|
| V1 (DPO 原始) | `../qwen3vl-dpo/` | 原始 DPO 实验 |
| V2 (FCPO ms-swift) | `../qwen3vl-dpo-v2/` | FCPO pipeline + ms-swift 实验 |
| V3 (FCPO LF) | `../qwen3vl-dpo-v3/` | LlamaFactory FCPO 17 实验 |
| SFT | `../qwen3vl-sft/` | SFT 训练 |
| 评估框架 | `../finmme-benchmark/` | FinMME 评估 |

---

## 行为准则

### 1. 统一使用 LlamaFactory

不再使用 ms-swift 做 DPO 训练和推理。所有实验统一 LlamaFactory 0.9.5。

### 2. 评估标准升级

- 关键实验必须跑 **L3 (1000 样本)**，不仅仅是 L2 (200)
- 写入论文的实验必须 **3 seed + paired bootstrap**
- Top-3 实验用 **GPT-5 交叉 Judge**

### 3. 完整记录

- 每个实验在 `experiments/` 下建 MD
- 维护 `experiments/STATUS.md` 全局进度
- 训练配置放 `configs/`

### 4. 继承 V2 通用规则

- 不修改 V1/V2/V3 项目的文件
- 共享机先查 GPU 占用
- API 大批量前先测 10 条
- SSH 命令先小规模验证

---

## 目录结构

```
qwen3vl-dpo-v4/
├── CLAUDE.md              # 本文件
├── 00-FCPO实验复盘.md     # V2/V3 完整教训
├── 01-实验计划.md          # V4 方案
├── 02-服务器资源.md        # 服务器配置
├── 03-API配置.md           # API keys
├── experiments/            # 实验记录
│   └── STATUS.md           # 全局进度
├── configs/                # 训练配置
├── scripts/                # 脚本
├── data/                   # 数据
└── results/                # 评估结果
```
