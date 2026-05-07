# FinSumm

面向金融图表理解与摘要的视觉语言模型项目。包含数据合成 / 标注流水线、SFT + DPO + FCPO 三阶段训练、推理与 Benchmark 评估的完整代码与配置。

## 仓库结构

```
finsumm-project/
├── README.md
├── data/                                # FinChartSum 样例数据（50 条）
│   ├── charts/                          #   样例图
│   ├── finchartsum_sample.json
│   └── README.md
├── docs/                                # 顶层索引文档
└── src/
    ├── dataset_construction/            # 一、数据集构建
    │   ├── chart_synthesis/             #   合成图表 pipeline（v3/v4 合并版）
    │   │   ├── src/                     #     planning / fetching / rendering / orchestration
    │   │   ├── prompts/                 #     planner / coder / frontend prompt 模板
    │   │   ├── config/                  #     图表-库映射、数据源映射、指标定义
    │   │   ├── batch_configs/           #     批量生产配置（20 套）
    │   │   ├── scripts/                 #     run.py / generate_summary.py / data_processors
    │   │   └── docs/
    │   ├── ab_experiment/               #   A/B 参考信息验证
    │   │   ├── ab_experiment.py
    │   │   ├── evaluate_ab.py
    │   │   └── README.md
    │   └── annotation/
    │       ├── finchart/                #   FinChart 标注系统（Node.js 源码 + 一份导出）
    │       └── finmme/                  #   FinMME 标注系统（含 1000 条最终标注产物，剔除图片）
    │
    ├── training/                        # 二、训练
    │   ├── sft/                         #   (a) SFT  —  LLaMA-Factory + Qwen3-VL-8B LoRA
    │   │   ├── configs/                 #     qwen3vl_lora_sft.yaml / ds_zero2.json
    │   │   ├── scripts/                 #     train_full.sh / convert_all_data.py
    │   │   ├── docker/                  #     Dockerfile / docker-compose.yml
    │   │   ├── data/                    #     训练数据（all_train/val.json + dataset_info）
    │   │   └── CLAUDE.md
    │   ├── dpo/                         #   (b) DPO  —  偏好对学习
    │   │   ├── configs/                 #     dpo_exp001.yaml / qwen3vl_lora_dpo.yaml
    │   │   ├── scripts/                 #     候选生成 / 偏好对选择 / 推理
    │   │   ├── data/                    #     dpo_train_1700.json (8MB) 等
    │   │   └── CLAUDE.md
    │   └── fcpo/                        #   (c) FCPO  —  Fact-Calibrated Preference Optimization
    │       ├── configs/
    │       ├── scripts/                 #     h20_fcpo_*.sh / ablation/
    │       ├── data_pipeline/           #     compute_r_fact_llm.py / build_fcpo_data.py / score_candidates.py
    │       ├── data/                    #     fcpo_merged_*.json 等
    │       └── docs/                    #     00-FCPO实验复盘 / 04-数据构建Pipeline / 06-训练配置教训 等
    │
    ├── inference/                       # 三-1 推理脚本
    │   ├── lora_inference_8gpu.py       #     自研 LoRA 推理（8 卡）
    │   ├── dpo_inference_bilingual.py   #     DPO/FCPO 中英双语推理
    │   ├── api_inference_*.py           #     闭源 API 推理（GPT-5.4 / Gemini / Kimi 等）
    │   ├── base_inference_8gpu.py       #     基线模型推理
    │   └── INFERENCE_PARAMS.md
    │
    └── evaluation/                      # 三-2 Benchmark 评估
        ├── evaluators/
        │   ├── factscore_v2.py / v3.py  #     FactScore（自定义事实一致性指标）
        │   ├── judge_llm.py             #     LLM-as-Judge（Gemini-2.5-Flash）
        │   ├── traditional.py           #     BLEU / ROUGE / METEOR / CIDEr
        │   └── gemini_client.py
        ├── benchmark_full_1000.py       #     全量评估入口
        ├── benchmark_7checkpoints.py    #     多 checkpoint 对比
        ├── batch_eval_7ckpt.sh
        ├── dataset_index_*.json         #     评估集索引
        └── EVALUATION.md
```

## 完整训练流程

```
原始公开数据（FRED/yfinance/...）
        │
        ▼
┌──────────────────────────────────────┐
│ 1. dataset_construction/             │
│   chart_synthesis  → 合成 ~9K 图表    │
│   ab_experiment    → 验证参考信息有效 │
│   annotation       → 人工标注 ~6.4K   │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ 2(a). training/sft/                  │
│   Qwen3-VL-8B + LoRA r=256           │
│   ~6.4K samples / 5 epochs / lr 1e-4 │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ 2(b). training/dpo/                  │
│   候选生成 → 偏好对选择              │
│   ~1.7K pairs / 1 epoch              │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ 2(c). training/fcpo/                 │
│   Fact-Calibrated 偏好优化           │
│   per-sample margin (γ=4.0)          │
│   1.7K pairs / 1 epoch / β=0.1       │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ 3. inference/  +  evaluation/        │
│   FinChartSum 1000-sample benchmark  │
│   LLM-Score + 6 个传统 NLG 指标       │
└──────────────────────────────────────┘
```

## 环境

- 训练：8×H20 (FCPO) / 8×RTX4090 (SFT)
- 框架：LLaMA-Factory + DeepSpeed ZeRO-2 + transformers
- Python 3.10 + flash-attn

具体环境配置见各阶段 `Dockerfile`、`CLAUDE.md` 和 `06-训练配置教训.md`。

## 数据与模型

- 仓库内已含小体积训练 / 偏好对 / 评估索引 JSON（< 15 MB 单文件）
- 大体积候选集、源 facts、训练图片仅在 GPU 服务器保留；各 `data/README.md` 列出对应路径
- GPU 服务器路径前缀：`$DATA_ROOT/{sft,dpo,dpo-v4}/`、`$DATA_ROOT/benchmark/`

## 关键文档

| 文档 | 说明 |
|------|------|
| `src/training/sft/CLAUDE.md` | SFT 阶段说明 |
| `src/training/dpo/CLAUDE.md` | DPO 阶段说明 |
| `src/training/fcpo/docs/00-FCPO实验复盘.md` | FCPO 实验全过程复盘 |
| `src/training/fcpo/docs/04-数据构建Pipeline.md` | FCPO 数据构建详细流程 |
| `src/training/fcpo/docs/05-Fact评分Pipeline对比.md` | FactScore 各版本对比 |
| `src/training/fcpo/docs/06-训练配置教训.md` | 调参 / 显存 / 配置坑点 |
| `src/training/fcpo/docs/02-服务器资源.md` | H20 服务器资源说明 |
| `src/training/fcpo/docs/03-API配置.md` | 评估 / 标注 API key 与配置 |
| `src/training/fcpo/docs/08-评估结果STATUS.md` | FCPO R2 评估对比表 |
| `src/evaluation/EVALUATION.md` | 评估方法说明 |
| `src/inference/INFERENCE_PARAMS.md` | 推理参数对照 |

## API Key 与环境变量

仓库中所有出现 `<YOUR_API_KEY>` 占位符的地方都需在使用前替换为真实 key。涉及的服务：

- **apiyi (主用)** — `compute_r_fact_llm*.py` / `score_candidates.py` / `evaluate_ab.py` / `ab_experiment.py` / `generate_summary.py` / `api_inference_parallel.py` / 标注系统 `translate-analysis.js` / `generate-full-analysis-continue.js` 等
- **<YOUR_LLM_PROXY>** — `annotation/finchart` 早期标注脚本
- **<YOUR_LLM_PROXY>** — `annotation/finmme` / `chart_synthesis/config/llm_config.yaml`
- **OpenRouter / 其他直连 OpenAI** — `annotation/finchart/.env.example`

`annotation/{finchart,finmme}/.env.example` 已就位，复制为 `.env` 并填入自己的 key 即可（`.env` 已被 `.gitignore` 排除）。

## 已知论文-代码差异

以下是论文与本仓库实现的细节差异，以**仓库代码为准**：

1. **Judge 评估维度**：本仓库 `evaluation/evaluators/judge_llm.py` 实现的是 **4 维**加权（Faithfulness 35% / Completeness 30% / Analysis 25% / Conciseness 10%）。论文方法章节描述含 Logicality 共 5 维，但 Tab.main 的实际数据是按 4 维产出的。
2. **Judge 模型**：本仓库 `judge_llm.py` 默认使用 **`gemini-2.5-flash-lite-preview-09-2025`**。中文论文写 Gemini-2.5-Flash、英文论文写 GPT-4o，均为论文笔误，实际复现以代码默认为准。
3. **数据源适配器**：英文论文 §4.1 列了 World Bank，但 `chart_synthesis/src/capabilities/data_fetching/adapters.py` 实际实现的是 FRED / Baostock / YFinance / Efinance / CrossSectional 五个适配器（不含 World Bank）。
