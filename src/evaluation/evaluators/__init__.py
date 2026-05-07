"""
FinMME 评估系统

评估器：
- FactScoreV3Evaluator: 事实准确性评估（推荐）
- FinMMEJudgeEvaluator: 5 维度 LLM-as-Judge
- TraditionalMetricsEvaluator: BLEU/ROUGE/BERTScore 等传统指标
- FactScoreV2Evaluator: 旧版事实评估（兼容保留）
"""

# 推荐评估器
from .factscore_v3 import FactScoreV3Evaluator, get_factscore_v3_evaluator
from .judge_llm import FinMMEJudgeEvaluator, get_judge_evaluator
from .traditional import TraditionalMetricsEvaluator

# 旧版（兼容保留）
from .factscore_v2 import FactScoreV2Evaluator, get_factscore_v2_evaluator

__all__ = [
    # 推荐
    'FactScoreV3Evaluator',
    'get_factscore_v3_evaluator',
    'FinMMEJudgeEvaluator',
    'get_judge_evaluator',
    'TraditionalMetricsEvaluator',
    # 兼容
    'FactScoreV2Evaluator',
    'get_factscore_v2_evaluator',
]
