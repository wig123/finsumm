# A/B Experiment: Impact of Internal Reference Information on Chart Summarization Quality

**Experiment Date**: 2024-12-04

## Experiment Objective

Validate whether providing internal reference information (metadata + data summary) can improve generation quality in chart summarization tasks.

## Experiment Design

### Experiment Groups

| Group | Condition | Description |
|-------|-----------|-------------|
| **Group A** | System Prompt Only | Pure visual analysis, model relies solely on chart images |
| **Group B** | System Prompt + Internal Reference Information | Additionally provides chart metadata and data summary |

### Internal Reference Information Template

```
[Internal Reference Information]
The following information is provided solely to verify the accuracy of your visual analysis. Do not mention the existence of this reference information in your output.

[Metadata]
Chart Type: {chart_type}
Data Source: {data_source}
Time Range: {time_range}
Data Points: {data_points}

[Data Summary]
{data_summary}
```

### Experiment Parameters

- **Generation Model**: `gemini-2.5-flash-preview-09-2025`
- **Evaluation Model**: `gpt-5` (Judge)
- **Sample Size**: 100 charts (randomly sampled from batch_004)
- **Random Seed**: 42
- **Concurrency**: Generation 20, Evaluation 10

## Experiment Results

### Generation Phase Statistics

| Metric | Group A (Pure Visual) | Group B (+ Reference Information) | Difference |
|--------|-----------------------|-----------------------------------|------------|
| Success Rate | 100/100 | 100/100 | - |
| Average Tokens | 3,890 | 4,489 | +15% |
| Average Time | 13.03s | 10.73s | -18% |
| Average Analysis Length | 1,791 characters | 1,828 characters | +2% |

### Evaluation Results (GPT-5 Judge)

| Evaluation Dimension | Group A | Group B | Difference | Weight |
|----------------------|---------|---------|------------|--------|
| **Weighted Total Score** | **3.725** | **3.980** | **+0.255 (+6.85%)** | - |
| Faithfulness | 2.990 | 3.418 | **+0.428** | 30% |
| Completeness | 3.910 | 4.163 | +0.253 | 25% |
| Analysis | 3.730 | 3.980 | +0.250 | 20% |
| Logicality | 4.720 | 4.806 | +0.086 | 15% |
| Conciseness | 3.960 | 3.969 | +0.009 | 10% |

### Score Distribution

**Group A**:
- Weighted Total Score: min=1.0, max=4.7, std=0.521

**Group B**:
- Weighted Total Score: min=2.95, max=4.7, std=0.398

## Key Findings

1.  **Group B generally outperforms Group A**: Weighted total score increased by 6.85%, which is statistically significant.

2.  **Faithfulness improved most significantly**: +0.428 (14.3% improvement)
    -   After providing reference data, numerical accuracy significantly improved.
    -   Group A's average faithfulness was only 2.99, indicating significant errors in numerical recognition based purely on visual input.

3.  **Moderate improvement in completeness and analysis depth**: approximately +0.25
    -   With reference information, the model can cover more key data points.
    -   Analysis depth also increased accordingly.

4.  **Smaller difference in logicality and conciseness**:
    -   Structural quality is primarily determined by the system prompt.
    -   Reference information has limited impact on output format.

5.  **Group B results are more stable**:
    -   Standard deviation decreased from 0.521 to 0.398.
    -   Minimum score increased from 1.0 to 2.95.

## Conclusion

Providing internal reference information can significantly improve the quality of chart summarization, especially in terms of **numerical accuracy (faithfulness)**. This validates that combining structured data as auxiliary information is an effective strategy in VLM chart understanding tasks.

## File Structure

```
ab_experiment_20241204/
├── README.md                    # This document
├── ab_experiment.py             # Generation experiment script (async concurrent)
├── evaluate_ab.py               # Evaluation script (GPT-5 Judge)
├── ab_experiment_results/       # Generation results
│   ├── sample_list.json         # Sample list
│   ├── results_group_a.json     # Group A raw results
│   ├── results_group_b.json     # Group B raw results
│   ├── results_combined.json    # Paired comparison results
│   └── experiment_summary.json  # Generation statistics summary
└── ab_evaluation_results/       # Evaluation results
    ├── eval_group_a.json        # Group A evaluation details
    ├── eval_group_b.json        # Group B evaluation details
    └── evaluation_summary.json  # Evaluation statistics summary
```

## Reproduction Instructions

```bash
# 1. Run generation experiment
python ab_experiment.py

# 2. Run evaluation
python evaluate_ab.py
```

**Dependencies**:
- openai (AsyncOpenAI)
- Data processing module: `chart-synthesis-v3/scripts/data_processors/`
