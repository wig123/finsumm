# Document Index

## Phase Descriptions
- [SFT Phase](../src/training/sft/CLAUDE.md)
- [DPO Phase](../src/training/dpo/CLAUDE.md)
- [FCPO Phase](../src/training/fcpo/docs/CLAUDE.md)
- [Evaluation Methods](../src/evaluation/EVALUATION.md)
- [Inference Parameters](../src/inference/INFERENCE_PARAMS.md)

## FCPO Specific Documentation
| Document | Content |
|---|---|
| [00-FCPO Experiment Review](../src/training/fcpo/docs/00-fcpo-experiment-review.md) | Full process review, key decisions, and final solution |
| [01-Experiment Plan](../src/training/fcpo/docs/01-experiment-plan.md) | Experiment design and control groups |
| [02-Server Resources](../src/training/fcpo/docs/02-server-resources.md) | H20 Servers, Docker, VRAM allocation |
| [03-API Configuration](../src/training/fcpo/docs/03-api-configuration.md) | API keys and endpoints for evaluation / annotation |
| [04-Data Construction Pipeline](../src/training/fcpo/docs/04-data-construction-pipeline.md) | Candidate generation → Fact scoring → Preference pair construction |
| [05-Fact Scoring Pipeline Comparison](../src/training/fcpo/docs/05-fact-scoring-pipeline-comparison.md) | FactScore v1/v2/v3 comparison and selection |
| [06-Training Configuration Lessons](../src/training/fcpo/docs/06-training-configuration-lessons.md) | Learning rate / batch / gradient accumulation / OOM lessons |
| [07-Experiment Protocol](../src/training/fcpo/docs/07-experiment-protocol.md) | Final training hyperparameters and commands |

## Data Overview
- [SFT Data](../src/training/sft/data/) — Refer to `dataset_info.json`
- [DPO Data](../src/training/dpo/data/README.md) — In-repo file list + GPU large file paths
- [FCPO Data](../src/training/fcpo/data/README.md) — Same as above
- [Benchmark Examples](../data/README.md) — 50 FinChartSum examples

## Dataset Construction
- [Synthetic Chart README](../src/dataset_construction/chart_synthesis/README.md)
- [Synthetic Chart CLAUDE.md](../src/dataset_construction/chart_synthesis/CLAUDE.md)
- [A/B Experiment README](../src/dataset_construction/ab_experiment/README.md)
- [FinChart Annotation System README](../src/dataset_construction/annotation/finchart/README.md)
- [FinMME Annotation System README](../src/dataset_construction/annotation/finmme/README.md)
