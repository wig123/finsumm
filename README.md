# FinSumm

A visual language model project for financial chart understanding and summarization. Includes complete code and configurations for data synthesis/annotation pipelines, three-stage training (SFT + DPO + FCPO), inference, and benchmark evaluation.

## Repository Structure

```
finsumm-project/
├── README.md
├── data/                                # FinChartSum sample data (50 entries)
│   ├── charts/                          #   Sample charts
│   ├── finchartsum_sample.json
│   └── README.md
├── docs/                                # Top-level index documents
└── src/
    ├── dataset_construction/            # 1. Dataset Construction
    │   ├── chart_synthesis/             #   Chart synthesis pipeline (v3/v4 merged)
    │   │   ├── src/                     #     planning / fetching / rendering / orchestration
    │   │   ├── prompts/                 #     planner / coder / frontend prompt templates
    │   │   ├── config/                  #     chart-library mapping, data source mapping, metric definitions
    │   │   ├── batch_configs/           #     batch production configs (20 sets)
    │   │   ├── scripts/                 #     run.py / generate_summary.py / data_processors
    │   │   └── docs/
    │   ├── ab_experiment/               #   A/B reference information validation
    │   │   ├── ab_experiment.py
    │   │   ├── evaluate_ab.py
    │   │   └── README.md
    │   └── annotation/
    │       ├── finchart/                #   FinChart annotation system (Node.js source + one export)
    │       └── finmme/                  #   FinMME annotation system (contains 1000 final annotations, images excluded)
    │
    ├── training/                        # 2. Training
    │   ├── sft/                         #   (a) SFT  —  LLaMA-Factory + Qwen3-VL-8B LoRA
    │   │   ├── configs/                 #     qwen3vl_lora_sft.yaml / ds_zero2.json
    │   │   ├── scripts/                 #     train_full.sh / convert_all_data.py
    │   │   ├── docker/                  #     Dockerfile / docker-compose.yml
    │   │   ├── data/                    #     training data (all_train/val.json + dataset_info)
    │   │   └── CLAUDE.md
    │   ├── dpo/                         #   (b) DPO  —  preference pair learning
    │   │   ├── configs/                 #     dpo_exp001.yaml / qwen3vl_lora_dpo.yaml
    │   │   ├── scripts/                 #     candidate generation / preference pair selection / inference
    │   │   ├── data/                    #     dpo_train_1700.json (8MB) etc.
    │   │   └── CLAUDE.md
    │   └── fcpo/                        #   (c) FCPO  —  Fact-Calibrated Preference Optimization
    │       ├── configs/
    │       ├── scripts/                 #     h20_fcpo_*.sh / ablation/
    │       ├── data_pipeline/           #     compute_r_fact_llm.py / build_fcpo_data.py / score_candidates.py
    │       ├── data/                    #     fcpo_merged_*.json etc.
    │       └── docs/                    #     00-FCPO Experiment Review / 04-Data Construction Pipeline / 06-Training Configuration Lessons etc.
    │
    ├── inference/                       # 3-1 Inference Scripts
    │   ├── lora_inference_8gpu.py       #     Custom LoRA inference (8 GPUs)
    │   ├── dpo_inference_bilingual.py   #     DPO/FCPO bilingual inference
    │   ├── api_inference_*.py           #     Closed-source API inference (GPT-5.4 / Gemini / Kimi etc.)
    │   ├── base_inference_8gpu.py       #     Baseline model inference
    │   └── INFERENCE_PARAMS.md
    │
    └── evaluation/                      # 3-2 Benchmark Evaluation
        ├── evaluators/
        │   ├── factscore_v2.py / v3.py  #     FactScore (custom factual consistency metric)
        │   ├── judge_llm.py             #     LLM-as-Judge (Gemini-2.5-Flash)
        │   ├── traditional.py           #     BLEU / ROUGE / METEOR / CIDEr
        │   └── gemini_client.py
        ├── benchmark_full_1000.py       #     Full evaluation entry point
        ├── benchmark_7checkpoints.py    #     Multi-checkpoint comparison
        ├── batch_eval_7ckpt.sh
        ├── dataset_index_*.json         #     Evaluation set index
        └── EVALUATION.md
```

## Full Training Workflow

```
Raw public data (FRED/yfinance/...)
        │
        ▼
┌──────────────────────────────────────┐
│ 1. dataset_construction/             │
│   chart_synthesis  → synthesize ~9K charts │
│   ab_experiment    → validate reference info effectiveness │
│   annotation       → manual annotation ~6.4K │
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
│   candidate generation → preference pair selection │
│   ~1.7K pairs / 1 epoch              │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ 2(c). training/fcpo/                 │
│   Fact-Calibrated preference optimization │
│   per-sample margin (γ=4.0)          │
│   1.7K pairs / 1 epoch / β=0.1       │
└──────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ 3. inference/  +  evaluation/        │
│   FinChartSum 1000-sample benchmark  │
│   LLM-Score + 6 traditional NLG metrics │
└──────────────────────────────────────┘
```

## Environment

- Training: 8×H20 (FCPO) / 8×RTX4090 (SFT)
- Framework: LLaMA-Factory + DeepSpeed ZeRO-2 + transformers
- Python 3.10 + flash-attn

Specific environment configurations can be found in `Dockerfile`, `CLAUDE.md`, and `06-training-configuration-lessons.md` for each stage.

## Data and Models

- The repository already includes small-volume training / preference pair / evaluation index JSON files (< 15 MB single file).
- Large-volume candidate sets, source facts, and training images are only kept on the GPU server; corresponding paths are listed in each `data/README.md`.
- GPU server path prefixes: `$DATA_ROOT/{sft,dpo,dpo-v4}/`, `$DATA_ROOT/benchmark/`

## Key Documents

| Document | Description |
|------|------|
| `src/training/sft/CLAUDE.md` | SFT Stage Description |
| `src/training/dpo/CLAUDE.md` | DPO Stage Description |
| `src/training/fcpo/docs/00-fcpo-experiment-review.md` | FCPO Experiment Full Retrospective |
| `src/training/fcpo/docs/04-data-construction-pipeline.md` | FCPO Data Construction Detailed Workflow |
| `src/training/fcpo/docs/05-fact-scoring-pipeline-comparison.md` | FactScore Version Comparison |
| `src/training/fcpo/docs/06-training-configuration-lessons.md` | Parameter Tuning / VRAM / Configuration Pitfalls |
| `src/training/fcpo/docs/02-server-resources.md` | H20 Server Resource Description |
| `src/training/fcpo/docs/03-api-configuration.md` | Evaluation / Annotation API Key and Configuration |
| `src/training/fcpo/docs/08-evaluation-results-status.md` | FCPO R2 Evaluation Comparison Table |
| `src/evaluation/EVALUATION.md` | Evaluation Method Description |
| `src/inference/INFERENCE_PARAMS.md` | Inference Parameter Reference |

## API Keys and Environment Variables

All occurrences of the `<YOUR_API_KEY>` placeholder in the repository must be replaced with a real key before use. Services involved:

- **apiyi (primary)** — `compute_r_fact_llm*.py` / `score_candidates.py` / `evaluate_ab.py` / `ab_experiment.py` / `generate_summary.py` / `api_inference_parallel.py` / annotation system `translate-analysis.js` / `generate-full-analysis-continue.js`, etc.
- **<YOUR_LLM_PROXY>** — `annotation/finchart` early annotation scripts
- **<YOUR_LLM_PROXY>** — `annotation/finmme` / `chart_synthesis/config/llm_config.yaml`
- **OpenRouter / Other direct OpenAI connections** — `annotation/finchart/.env.example`

`annotation/{finchart,finmme}/.env.example` is already in place. Copy it to `.env` and fill in your own key (`.env` has been excluded by `.gitignore`).
