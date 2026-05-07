"""
A/B 实验结果评估脚本
==================
使用 GPT-5 作为 Judge 对两组结果进行多维度评估
"""

import json
import asyncio
import base64
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from openai import AsyncOpenAI

# ============== 配置 ==============

API_KEY = '<YOUR_API_KEY>'
BASE_URL = '<YOUR_LLM_PROXY>/v1'
JUDGE_MODEL = 'gpt-5'

MAX_CONCURRENCY = 10  # 评估并发数

# 路径配置
RESULTS_DIR = Path("<WORKSPACE>/合成图表/test/ab_experiment_results")
CHART_BASE_DIR = Path("<WORKSPACE>/合成图表/chart-synthesis-v3/prog_2000/batch_004")
OUTPUT_DIR = Path("<WORKSPACE>/合成图表/test/ab_evaluation_results")

# ============== 评估 Prompt ==============

JUDGE_PROMPT = """You are an expert financial analyst evaluating chart analysis summaries.

## Task
Evaluate the quality of a chart analysis summary by comparing it with the actual chart image.

## Chart Image
[Attached]

## Candidate Summary (to be evaluated)
{prediction}

## Evaluation Dimensions & Rubrics

### 1. Faithfulness (忠实度) - Weight: 30%
How accurately does the summary reflect the chart data?

| Score | Criteria |
|-------|----------|
| 5 | All numerical values, trends, and comparisons are correct. No hallucinations. |
| 4 | Minor numerical errors in 1-2 values. No significant hallucinations. |
| 3 | Some numerical errors or 1 minor hallucination. Core trends correct. |
| 2 | Multiple significant errors or hallucinations. Some trends misrepresented. |
| 1 | Pervasive errors. Major hallucinations. Fundamentally misrepresents the chart. |

### 2. Completeness (覆盖度) - Weight: 25%
How well does the summary cover the key information in the chart?

| Score | Criteria |
|-------|----------|
| 5 | Covers all key data points, main trend, extrema, and important comparisons. |
| 4 | Covers most key information. Missing 1 minor data point. |
| 3 | Covers core trend and some key values. Missing 2-3 significant points. |
| 2 | Only covers partial information. Missing major trends or key extrema. |
| 1 | Severely incomplete. Missing most important information. |

### 3. Analysis (分析深度) - Weight: 20%
Does the summary provide meaningful insights beyond mere data description?

| Score | Criteria |
|-------|----------|
| 5 | Provides insightful analysis with business implications, risk factors, and actionable thresholds. |
| 4 | Good analysis with clear implications. Missing some depth in risk discussion. |
| 3 | Basic analysis present. Insights are somewhat generic. |
| 2 | Minimal analysis. Mostly restates numbers without interpretation. |
| 1 | No meaningful analysis. Pure data regurgitation. |

### 4. Logicality (逻辑性) - Weight: 15%
Is the summary well-organized and logically coherent?

| Score | Criteria |
|-------|----------|
| 5 | Clear 4-section structure. Logical flow from description to insight. No contradictions. |
| 4 | Good structure. Minor organizational issues. Coherent overall. |
| 3 | Acceptable structure. Some logical gaps or unclear transitions. |
| 2 | Poor organization. Contains contradictions or illogical statements. |
| 1 | Disorganized. Multiple contradictions. Hard to follow. |

### 5. Conciseness (简洁性) - Weight: 10%
Is the summary concise without unnecessary redundancy?

| Score | Criteria |
|-------|----------|
| 5 | Highly efficient. Every sentence adds value. No redundancy. |
| 4 | Mostly concise. Minor redundancy (1-2 repeated points). |
| 3 | Acceptable length. Some verbose passages or repetition. |
| 2 | Noticeably verbose. Multiple redundant statements. |
| 1 | Extremely verbose or padded. Significant irrelevant content. |

## Output Format (Strict JSON)
{{
  "faithfulness": {{
    "score": <1-5>,
    "evidence": "Specific examples supporting the score"
  }},
  "completeness": {{
    "score": <1-5>,
    "evidence": "What was covered/missed"
  }},
  "analysis": {{
    "score": <1-5>,
    "evidence": "Quality of insights provided"
  }},
  "logicality": {{
    "score": <1-5>,
    "evidence": "Structure and coherence assessment"
  }},
  "conciseness": {{
    "score": <1-5>,
    "evidence": "Redundancy and efficiency assessment"
  }},
  "overall_comment": "Brief overall assessment in 1-2 sentences"
}}

## Important Guidelines
- Evaluate based on the ACTUAL CHART IMAGE
- Be objective and critical - avoid score inflation
- Focus on whether the summary accurately represents what's in the chart
"""

DIMENSION_WEIGHTS = {
    "faithfulness": 0.30,
    "completeness": 0.25,
    "analysis": 0.20,
    "logicality": 0.15,
    "conciseness": 0.10
}


# ============== 工具函数 ==============

def load_json(path: Path) -> Dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def encode_image(image_path: Path) -> str:
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def extract_json_from_response(content: str) -> Dict:
    """从响应中提取 JSON"""
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        parts = content.split("```")
        if len(parts) >= 2:
            content = parts[1].strip()
    return json.loads(content)


async def evaluate_single(
    client: AsyncOpenAI,
    chart_id: str,
    analysis: str,
    image_path: Path,
    group: str,
    semaphore: asyncio.Semaphore
) -> Dict:
    """异步评估单个样本"""
    async with semaphore:
        try:
            # 编码图片
            base64_image = encode_image(image_path)

            # 构建 prompt
            prompt = JUDGE_PROMPT.format(prediction=analysis)

            # 调用 API
            start_time = datetime.now()
            completion = await client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                temperature=0.0,
                max_tokens=4096,
                response_format={"type": "json_object"}
            )
            duration = (datetime.now() - start_time).total_seconds()

            # 解析结果
            content = completion.choices[0].message.content
            result = extract_json_from_response(content)

            # 计算加权分数
            dimensions = ["faithfulness", "completeness", "analysis", "logicality", "conciseness"]
            scores = {}
            weighted_sum = 0.0

            for dim in dimensions:
                dim_data = result.get(dim, {})
                score = dim_data.get("score", 3)
                scores[dim] = {
                    "score": score,
                    "evidence": dim_data.get("evidence", ""),
                    "weight": DIMENSION_WEIGHTS[dim]
                }
                weighted_sum += score * DIMENSION_WEIGHTS[dim]

            return {
                "chart_id": chart_id,
                "group": group,
                "scores": scores,
                "weighted_score": round(weighted_sum, 3),
                "normalized_score": round(weighted_sum / 5.0, 3),
                "overall_comment": result.get("overall_comment", ""),
                "duration_s": round(duration, 2),
                "status": "success"
            }

        except Exception as e:
            return {
                "chart_id": chart_id,
                "group": group,
                "status": "error",
                "error": str(e)
            }


async def run_evaluation():
    """运行评估"""
    print(f"📊 开始评估 A/B 实验结果")
    print(f"   Judge 模型: {JUDGE_MODEL}")
    print(f"   最大并发: {MAX_CONCURRENCY}")
    print()

    # 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 加载实验结果
    results_combined = load_json(RESULTS_DIR / "results_combined.json")
    print(f"📁 加载 {len(results_combined)} 个配对结果")

    # 初始化客户端
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    # 准备评估任务
    tasks = []
    for item in results_combined:
        chart_id = item["chart_id"]
        image_path = CHART_BASE_DIR / chart_id / "artifacts" / "chart.png"

        if not image_path.exists():
            print(f"   ⚠️ 图片不存在: {chart_id}")
            continue

        # A 组评估
        if item["group_a"]["status"] == "success":
            tasks.append(evaluate_single(
                client, chart_id, item["group_a"]["analysis"],
                image_path, "A", semaphore
            ))

        # B 组评估
        if item["group_b"]["status"] == "success":
            tasks.append(evaluate_single(
                client, chart_id, item["group_b"]["analysis"],
                image_path, "B", semaphore
            ))

    print(f"🚀 启动 {len(tasks)} 个评估任务...")
    start_time = datetime.now()

    # 并发执行
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    total_duration = (datetime.now() - start_time).total_seconds()

    # 分离结果
    eval_a = []
    eval_b = []

    for result in all_results:
        if isinstance(result, Exception):
            print(f"   ❌ 异常: {result}")
            continue
        if result["group"] == "A":
            eval_a.append(result)
        else:
            eval_b.append(result)

    # 统计
    success_a = sum(1 for r in eval_a if r.get("status") == "success")
    success_b = sum(1 for r in eval_b if r.get("status") == "success")

    print()
    print(f"⏱️  总耗时: {total_duration:.1f}s")
    print(f"   A组: {success_a}/{len(eval_a)} 成功")
    print(f"   B组: {success_b}/{len(eval_b)} 成功")

    # 保存结果
    save_evaluation_results(eval_a, eval_b)

    print()
    print(f"✅ 评估完成!")
    print(f"   结果保存在: {OUTPUT_DIR}")


def save_evaluation_results(eval_a: List[Dict], eval_b: List[Dict]):
    """保存评估结果"""
    import numpy as np

    # 保存详细结果
    with open(OUTPUT_DIR / "eval_group_a.json", 'w', encoding='utf-8') as f:
        json.dump(eval_a, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "eval_group_b.json", 'w', encoding='utf-8') as f:
        json.dump(eval_b, f, ensure_ascii=False, indent=2)

    # 计算统计
    def calc_stats(results):
        successful = [r for r in results if r.get("status") == "success"]
        if not successful:
            return {}

        weighted_scores = [r["weighted_score"] for r in successful]
        dimension_scores = {dim: [] for dim in DIMENSION_WEIGHTS.keys()}

        for r in successful:
            for dim in dimension_scores:
                if dim in r["scores"]:
                    dimension_scores[dim].append(r["scores"][dim]["score"])

        return {
            "count": len(results),
            "success": len(successful),
            "weighted_score": {
                "mean": round(np.mean(weighted_scores), 3),
                "std": round(np.std(weighted_scores), 3),
                "min": round(min(weighted_scores), 3),
                "max": round(max(weighted_scores), 3)
            },
            "dimension_scores": {
                dim: {
                    "mean": round(np.mean(scores), 3),
                    "std": round(np.std(scores), 3)
                }
                for dim, scores in dimension_scores.items() if scores
            }
        }

    summary = {
        "experiment_info": {
            "judge_model": JUDGE_MODEL,
            "timestamp": datetime.now().isoformat(),
            "dimension_weights": DIMENSION_WEIGHTS
        },
        "group_a": {
            "description": "仅系统提示词（纯视觉分析）",
            "stats": calc_stats(eval_a)
        },
        "group_b": {
            "description": "系统提示词 + 内部参考信息（带数据辅助）",
            "stats": calc_stats(eval_b)
        }
    }

    # 计算差异
    if summary["group_a"]["stats"] and summary["group_b"]["stats"]:
        a_mean = summary["group_a"]["stats"]["weighted_score"]["mean"]
        b_mean = summary["group_b"]["stats"]["weighted_score"]["mean"]
        summary["comparison"] = {
            "weighted_score_diff": round(b_mean - a_mean, 3),
            "weighted_score_diff_pct": round((b_mean - a_mean) / a_mean * 100, 2) if a_mean else 0,
            "dimension_diffs": {}
        }

        for dim in DIMENSION_WEIGHTS.keys():
            a_dim = summary["group_a"]["stats"]["dimension_scores"].get(dim, {}).get("mean", 0)
            b_dim = summary["group_b"]["stats"]["dimension_scores"].get(dim, {}).get("mean", 0)
            summary["comparison"]["dimension_diffs"][dim] = round(b_mean - a_mean, 3)

    with open(OUTPUT_DIR / "evaluation_summary.json", 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 打印摘要
    print()
    print("=" * 60)
    print("评估结果摘要")
    print("=" * 60)

    if summary["group_a"]["stats"] and summary["group_b"]["stats"]:
        a_stats = summary["group_a"]["stats"]
        b_stats = summary["group_b"]["stats"]

        print(f"\n{'指标':<20} {'A组(纯视觉)':<15} {'B组(+参考)':<15} {'差异':<10}")
        print("-" * 60)

        a_ws = a_stats["weighted_score"]["mean"]
        b_ws = b_stats["weighted_score"]["mean"]
        diff = b_ws - a_ws
        print(f"{'加权总分':<20} {a_ws:<15.3f} {b_ws:<15.3f} {diff:+.3f}")

        for dim in DIMENSION_WEIGHTS.keys():
            a_dim = a_stats["dimension_scores"].get(dim, {}).get("mean", 0)
            b_dim = b_stats["dimension_scores"].get(dim, {}).get("mean", 0)
            diff = b_dim - a_dim
            print(f"{dim:<20} {a_dim:<15.3f} {b_dim:<15.3f} {diff:+.3f}")


def main():
    asyncio.run(run_evaluation())


if __name__ == "__main__":
    main()
