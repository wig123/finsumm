"""
FinMME-Judge 评估器
基于 LVLM-as-a-judge 的多维 1-5 分评价

评估维度：
1. Faithfulness（忠实度）- 权重 35%
2. Completeness（覆盖度）- 权重 30%
3. Analysis（分析深度）- 权重 25%
4. Conciseness（简洁性）- 权重 10%
"""

import os
import json
import base64
import time
from typing import Dict, List, Optional, Union
from pathlib import Path
import requests


class OpenAIClient:
    """OpenAI API 客户端（用于 GPT-5）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "<YOUR_LLM_PROXY>/v1",
        model: str = "gemini-2.5-flash-lite-preview-09-2025",
        max_retries: int = 3,
        timeout: int = 120
    ):
        """
        初始化 OpenAI 客户端

        Args:
            api_key: API密钥
            base_url: API base URL
            model: 模型名称
            max_retries: 最大重试次数
            timeout: 请求超时时间
        """
        # API 易的 API key
        self.api_key = api_key or os.getenv("APIYI_API_KEY") or "<YOUR_API_KEY>"

        self.base_url = base_url.rstrip('/')
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def _encode_image(self, image_path: Union[str, Path]) -> str:
        """将图片编码为 base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def chat(
        self,
        prompt: str,
        image_path: Optional[Union[str, Path]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 16000,  # GPT-5 需要更多 token（含推理 token）
        json_mode: bool = True
    ) -> Dict:
        """调用 OpenAI API"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if image_path:
            image_b64 = self._encode_image(image_path)
            img_format = Path(image_path).suffix.lower()
            media_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
            }.get(img_format, 'image/jpeg')

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_b64}"}
                    },
                    {"type": "text", "text": prompt}
                ]
            })
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()

                return {
                    "content": result["choices"][0]["message"]["content"],
                    "usage": result.get("usage", {})
                }
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"API 调用失败，{wait_time}秒后重试... ({attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"OpenAI API 调用失败: {e}")

    def extract_json(self, response: Dict) -> Dict:
        """从响应中提取 JSON"""
        content = response["content"]

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1].strip()

        return json.loads(content)


class FinMMEJudgeEvaluator:
    """FinMME-Judge 评估器 - LVLM-as-a-judge 多维评分"""

    # 维度权重
    DIMENSION_WEIGHTS = {
        "faithfulness": 0.35,
        "completeness": 0.30,
        "analysis": 0.25,
        "conciseness": 0.10
    }

    # 详细的 Rubric
    JUDGE_PROMPT = """You are an expert financial analyst evaluating chart summaries.

## Task
Evaluate the candidate summary against the chart image and reference summary.

## Inputs
**Chart Image**: [Attached]

**Reference Summary (Ground Truth)**:
{reference}

**Candidate Summary (Model Output)**:
{prediction}

## Evaluation Dimensions & Rubrics

### 1. Faithfulness (忠实度) - Weight: 35%
How accurately does the summary reflect the chart data?

| Score | Criteria |
|-------|----------|
| 5 | All numerical values, trends, and comparisons are correct (within 3% tolerance). No hallucinations. |
| 4 | Minor numerical errors (3-5% deviation) in 1-2 values. No significant hallucinations. |
| 3 | Some numerical errors (5-10% deviation) or 1 minor hallucination. Core trends correct. |
| 2 | Multiple significant errors or hallucinations. Some trends misrepresented. |
| 1 | Pervasive errors. Major hallucinations. Fundamentally misrepresents the chart. |

### 2. Completeness (覆盖度) - Weight: 30%
How well does the summary cover the key information in the chart?

| Score | Criteria |
|-------|----------|
| 5 | Covers all key data points, main trend, extrema, and important comparisons. |
| 4 | Covers most key information. Missing 1 minor data point. |
| 3 | Covers core trend and some key values. Missing 2-3 significant points. |
| 2 | Only covers partial information. Missing major trends or key extrema. |
| 1 | Severely incomplete. Missing most important information. |

### 3. Analysis (分析深度) - Weight: 25%
Does the summary provide meaningful insights beyond mere data description?

| Score | Criteria |
|-------|----------|
| 5 | Provides insightful analysis with business implications, risk factors, and actionable thresholds. |
| 4 | Good analysis with clear implications. Missing some depth in risk discussion. |
| 3 | Basic analysis present. Insights are somewhat generic. |
| 2 | Minimal analysis. Mostly restates numbers without interpretation. |
| 1 | No meaningful analysis. Pure data regurgitation. |

### 4. Conciseness (简洁性) - Weight: 10%
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
  "conciseness": {{
    "score": <1-5>,
    "evidence": "Redundancy and efficiency assessment"
  }},
  "overall_comment": "Brief overall assessment in 1-2 sentences"
}}

## Important Guidelines
- Focus primarily on the CHART for faithfulness verification
- Use reference as a quality benchmark, not absolute truth
- Treat numerical differences within 3% relative error as acceptable
- Do NOT reward length for its own sake
- Be objective and critical - avoid score inflation
"""

    def __init__(
        self,
        model: str = "gemini-2.5-flash-lite-preview-09-2025",
        api_key: Optional[str] = None,
        base_url: str = "<YOUR_LLM_PROXY>/v1"
    ):
        """
        初始化评估器

        Args:
            model: 模型名称
            api_key: API 密钥
            base_url: API base URL
        """
        self.client = OpenAIClient(
            api_key=api_key,
            base_url=base_url,
            model=model
        )
        self.weights = self.DIMENSION_WEIGHTS.copy()

    def set_weights(self, weights: Dict[str, float]):
        """设置自定义权重"""
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"权重之和必须为 1.0，当前为 {total}")
        self.weights = weights

    def evaluate(
        self,
        prediction: str,
        reference: str,
        image_path: Optional[str] = None
    ) -> Dict:
        """
        评估单个样本

        Args:
            prediction: 模型生成的文本
            reference: 参考文本
            image_path: 图表图片路径

        Returns:
            评估结果
        """
        prompt = self.JUDGE_PROMPT.format(
            reference=reference,
            prediction=prediction
        )

        # 调用多模态模型（GPT-5 需要更多 token 用于推理）
        response = self.client.chat(
            prompt=prompt,
            image_path=image_path if image_path and Path(image_path).exists() else None,
            temperature=0.0,
            max_tokens=16000,
            json_mode=True
        )

        result = self.client.extract_json(response)

        # 计算加权总分
        dimensions = ["faithfulness", "completeness", "analysis", "conciseness"]
        scores = {}
        weighted_sum = 0.0

        for dim in dimensions:
            dim_data = result.get(dim, {})
            score = dim_data.get("score", 3)
            scores[dim] = {
                "score": score,
                "evidence": dim_data.get("evidence", ""),
                "weight": self.weights[dim]
            }
            weighted_sum += score * self.weights[dim]

        return {
            "scores": scores,
            "weighted_score": weighted_sum,
            "normalized_score": weighted_sum / 5.0,  # 归一化到 0-1
            "overall_comment": result.get("overall_comment", "")
        }

    def evaluate_batch(self, samples: List[Dict]) -> Dict:
        """
        批量评估

        Args:
            samples: 样本列表

        Returns:
            汇总评估结果
        """
        import numpy as np

        all_metrics = []
        dimension_scores = {dim: [] for dim in self.weights.keys()}

        for sample in samples:
            try:
                metrics = self.evaluate(
                    prediction=sample.get("generated_text", ""),
                    reference=sample.get("ground_truth", ""),
                    image_path=sample.get("image_path")
                )
                metrics["sample_id"] = sample.get("id", "")
                all_metrics.append(metrics)

                # 收集各维度分数
                for dim in dimension_scores:
                    score = metrics["scores"].get(dim, {}).get("score", 0)
                    dimension_scores[dim].append(score)

            except Exception as e:
                print(f"评估失败 {sample.get('id', '')}: {e}")
                all_metrics.append({
                    "sample_id": sample.get("id", ""),
                    "error": str(e)
                })

        # 计算汇总统计
        valid_metrics = [m for m in all_metrics if "error" not in m]

        summary = {
            "avg_weighted_score": np.mean([m["weighted_score"] for m in valid_metrics]) if valid_metrics else 0,
            "avg_normalized_score": np.mean([m["normalized_score"] for m in valid_metrics]) if valid_metrics else 0,
            "dimension_averages": {
                dim: np.mean(scores) if scores else 0
                for dim, scores in dimension_scores.items()
            },
            "dimension_weights": self.weights,
            "total_samples": len(samples),
            "successful_evaluations": len(valid_metrics),
            "failed_evaluations": len(samples) - len(valid_metrics)
        }

        # 分数分布
        for dim in dimension_scores:
            scores = dimension_scores[dim]
            if scores:
                summary[f"{dim}_distribution"] = {
                    "min": min(scores),
                    "max": max(scores),
                    "median": np.median(scores),
                    "std": np.std(scores)
                }

        return {
            "summary": summary,
            "per_sample": all_metrics
        }


# 便捷函数
_global_judge: Optional[FinMMEJudgeEvaluator] = None


def get_judge_evaluator(model: str = "gpt-5") -> FinMMEJudgeEvaluator:
    """获取全局 Judge 评估器实例"""
    global _global_judge
    if _global_judge is None:
        _global_judge = FinMMEJudgeEvaluator(model=model)
    return _global_judge
