"""
FinMME-FactScore v3 评估器
改进版本：支持三种事实类型 (value, range, rank)
- value: 数值型，代码计算容差匹配
- range: 区间型，模型判断匹配
- rank: 排序型，模型判断匹配
"""

import json
import base64
import time
from typing import Dict, List, Optional, Union
from pathlib import Path
import requests


class FactScoreV3Evaluator:
    """FactScore v3 - 支持多类型事实的评估器"""

    RELATIVE_TOLERANCE = 0.03  # 3% 容差

    PROMPT = """你是金融图表分析专家。请完成以下任务：

【参考文本】
{reference}

【预测文本】
{prediction}

【任务】
1. 从参考文本中抽取**明确陈述的**事实 (ref_facts)
2. 从预测文本中抽取**明确陈述的**事实 (pred_facts)
3. 对每个 pred_fact 找对应的 ref_fact，并根据类型给出匹配信息

【事实类型】
- value: 精确数值（如"最高点150"、"增长20%"、"是A的2倍"）
- range: 区间（如"在8-9之间波动"、"价格区间100-200"）
- rank: 排序/极值（如"最高"、"最低"、"第二大"）

【抽取规则 - 非常重要】
1. 只抽取原文**字面明确给出**的数值，不做推断
2. 区间必须同时有明确的上下界才抽取
3. 不推断、不计算原文没有直接写出的数值
4. 如果不确定是否为精确值，宁可不抽取

【⚠️ match_result 字段格式要求 - 必须严格遵守】
match_result 字段**只能使用以下枚举值**，不能使用任何其他值：
- range 类型必须使用: "contained" | "overlap" | "disjoint"
- rank 类型必须使用: "correct" | "incorrect"
- value 类型不需要 match_result 字段

禁止使用: "correct"(range类型)、"match"、"close"、"approximate"、"no_match" 等非标准值！

【输出格式】严格 JSON：
{{
  "ref_facts": [
    {{"id": 1, "type": "value", "entity": "2023Q2销售额", "value": 150}},
    {{"id": 2, "type": "range", "entity": "价格波动区间", "min": 8.0, "max": 9.0}},
    {{"id": 3, "type": "rank", "entity": "Q2销售额排名", "rank": "highest"}}
  ],
  "pred_facts": [
    {{
      "id": 1,
      "type": "value",
      "entity": "Q2销售",
      "value": 148,
      "ref_id": 1,
      "chart": 150
    }},
    {{
      "id": 2,
      "type": "range",
      "entity": "价格区间",
      "min": 7.8,
      "max": 10.5,
      "ref_id": 2,
      "match_result": "overlap"
    }},
    {{
      "id": 3,
      "type": "rank",
      "entity": "Q2表现",
      "rank": "highest",
      "ref_id": 3,
      "match_result": "correct"
    }}
  ]
}}

【字段说明】
- type: "value" | "range" | "rank"
- value: 数值（仅 type=value 时使用）
- min/max: 区间边界（仅 type=range 时使用）
- rank: 排序描述（仅 type=rank 时使用），如 "highest", "lowest", "second", "third"
- ref_id: 语义匹配的 ref_fact id，无匹配则 null
- chart: 从图表读取的实际值（仅 type=value 时填写），无法读取则 null
- match_result: 见上方【match_result 字段格式要求】
"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "<YOUR_LLM_PROXY>/v1",
        model: str = "claude-sonnet-4-5-20250929",
        relative_tolerance: float = 0.03,
        max_retries: int = 3,
        timeout: int = 180
    ):
        self.api_key = api_key or "<YOUR_API_KEY>"
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.relative_tolerance = relative_tolerance
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

    def _call_api(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 16000
    ) -> Dict:
        """调用 API"""
        messages = []

        content = []
        if image_path and Path(image_path).exists():
            image_b64 = self._encode_image(image_path)
            img_format = Path(image_path).suffix.lower()
            media_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
            }.get(img_format, 'image/jpeg')

            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{image_b64}"}
            })

        content.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": content})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)

            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"API 调用失败，{wait_time}秒后重试... ({attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"API 调用失败: {e}")

    def _check_value_match(self, pred_value: float, target_value: float) -> bool:
        """检查数值是否在容差范围内"""
        if target_value == 0:
            return abs(pred_value) < 0.001
        relative_error = abs(pred_value - target_value) / abs(target_value)
        return relative_error <= self.relative_tolerance

    def _evaluate_value_fact(self, pf: Dict, ref_map: Dict) -> Dict:
        """评估 value 类型事实"""
        pred_value = pf.get("value")
        ref_id = pf.get("ref_id")
        chart_value = pf.get("chart")
        match_result = pf.get("match_result", "")

        is_correct = False
        match_type = None
        ref_value = None

        # 获取参考值
        if ref_id is not None and ref_id in ref_map:
            ref_fact = ref_map[ref_id]
            if ref_fact.get("type") == "value":
                ref_value = ref_fact.get("value")

        # 方案1: 信任 LLM 的 match_result（如果有 ref_id）
        llm_correct_keywords = ["correct", "match", "close", "approximate", "contained", "overlap"]
        if ref_id is not None and any(kw in str(match_result).lower() for kw in llm_correct_keywords):
            is_correct = True
            match_type = "llm_match"

        # 方案2: 数值精确匹配 pred_value vs ref_value
        if not is_correct and ref_value is not None and pred_value is not None:
            if self._check_value_match(pred_value, ref_value):
                is_correct = True
                match_type = "ref_match"

        # 方案3: 图表值与预测值匹配
        if not is_correct and chart_value is not None and pred_value is not None:
            if self._check_value_match(pred_value, chart_value):
                is_correct = True
                match_type = "chart_support"

        # 方案4: 当 pred_value=None 但 chart_value 与 ref_value 匹配
        # （评估模型有时把值放在 chart 字段而非 value 字段）
        if not is_correct and pred_value is None and chart_value is not None and ref_value is not None:
            if self._check_value_match(chart_value, ref_value):
                is_correct = True
                match_type = "chart_ref_match"

        return {
            "pred_id": pf["id"],
            "type": "value",
            "entity": pf.get("entity", ""),
            "pred_value": pred_value,
            "ref_id": ref_id,
            "ref_value": ref_value,
            "chart_value": chart_value,
            "match_result": match_result,
            "is_correct": is_correct,
            "match_type": match_type
        }

    def _evaluate_range_fact(self, pf: Dict, ref_map: Dict) -> Dict:
        """评估 range 类型事实（使用模型判断结果）"""
        ref_id = pf.get("ref_id")
        match_result = pf.get("match_result", "disjoint")

        # 使用模型给出的匹配结果
        # 兼容 LLM 可能返回的 "correct" (应该是 "contained" 或 "overlap")
        is_correct = match_result in ["contained", "overlap", "correct"]

        ref_range = None
        if ref_id is not None and ref_id in ref_map:
            ref_fact = ref_map[ref_id]
            if ref_fact.get("type") == "range":
                ref_range = {"min": ref_fact.get("min"), "max": ref_fact.get("max")}

        return {
            "pred_id": pf["id"],
            "type": "range",
            "entity": pf.get("entity", ""),
            "pred_range": {"min": pf.get("min"), "max": pf.get("max")},
            "ref_id": ref_id,
            "ref_range": ref_range,
            "match_result": match_result,
            "is_correct": is_correct,
            "match_type": "range_" + match_result if is_correct else None
        }

    def _evaluate_rank_fact(self, pf: Dict, ref_map: Dict) -> Dict:
        """评估 rank 类型事实（使用模型判断结果）"""
        ref_id = pf.get("ref_id")
        match_result = pf.get("match_result", "incorrect")

        # 使用模型给出的匹配结果
        is_correct = match_result == "correct"

        ref_rank = None
        if ref_id is not None and ref_id in ref_map:
            ref_fact = ref_map[ref_id]
            if ref_fact.get("type") == "rank":
                ref_rank = ref_fact.get("rank")

        return {
            "pred_id": pf["id"],
            "type": "rank",
            "entity": pf.get("entity", ""),
            "pred_rank": pf.get("rank"),
            "ref_id": ref_id,
            "ref_rank": ref_rank,
            "match_result": match_result,
            "is_correct": is_correct,
            "match_type": "rank_match" if is_correct else None
        }

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
        # 边界情况处理
        prediction = (prediction or "").strip()
        reference = (reference or "").strip()

        # 空参考文本 - 无法评估
        if not reference:
            return {
                "precision": None,  # None 表示无法评估，区别于 0.0
                "correct_count": 0,
                "total_pred_facts": 0,
                "total_ref_facts": 0,
                "hallucination_count": 0,
                "by_type": {"value": {}, "range": {}, "rank": {}},
                "ref_type_counts": {"value": 0, "range": 0, "rank": 0},
                "ref_facts": [],
                "pred_facts": [],
                "details": [],
                "skip_reason": "empty_reference"
            }

        # 空预测文本 - 无法评估
        if not prediction or len(prediction) < 10:
            return {
                "precision": None,  # None 表示无法评估
                "correct_count": 0,
                "total_pred_facts": 0,
                "total_ref_facts": 0,
                "hallucination_count": 0,
                "by_type": {"value": {}, "range": {}, "rank": {}},
                "ref_type_counts": {"value": 0, "range": 0, "rank": 0},
                "ref_facts": [],
                "pred_facts": [],
                "details": [],
                "skip_reason": "empty_prediction"
            }

        prompt = self.PROMPT.format(
            reference=reference,
            prediction=prediction
        )

        # 调用 API
        result = self._call_api(prompt, image_path)

        ref_facts = result.get("ref_facts", [])
        pred_facts = result.get("pred_facts", [])

        if not pred_facts:
            return {
                "precision": 0.0,
                "correct_count": 0,
                "total_pred_facts": 0,
                "total_ref_facts": len(ref_facts),
                "hallucination_count": 0,
                "by_type": {"value": {}, "range": {}, "rank": {}},
                "ref_type_counts": {"value": 0, "range": 0, "rank": 0},
                "ref_facts": ref_facts,
                "pred_facts": pred_facts,
                "details": []
            }

        # 构建 ref_facts 映射
        ref_map = {f["id"]: f for f in ref_facts}

        # 统计
        correct_count = 0
        type_stats = {
            "value": {"total": 0, "correct": 0, "ref_match": 0, "chart_support": 0},
            "range": {"total": 0, "correct": 0, "contained": 0, "overlap": 0},
            "rank": {"total": 0, "correct": 0}
        }
        details = []

        for pf in pred_facts:
            fact_type = pf.get("type", "value")

            if fact_type == "value":
                detail = self._evaluate_value_fact(pf, ref_map)
                type_stats["value"]["total"] += 1
                if detail["is_correct"]:
                    type_stats["value"]["correct"] += 1
                    if detail["match_type"] == "ref_match":
                        type_stats["value"]["ref_match"] += 1
                    elif detail["match_type"] == "chart_support":
                        type_stats["value"]["chart_support"] += 1

            elif fact_type == "range":
                detail = self._evaluate_range_fact(pf, ref_map)
                type_stats["range"]["total"] += 1
                if detail["is_correct"]:
                    type_stats["range"]["correct"] += 1
                    if detail["match_result"] == "contained":
                        type_stats["range"]["contained"] += 1
                    elif detail["match_result"] == "overlap":
                        type_stats["range"]["overlap"] += 1

            elif fact_type == "rank":
                detail = self._evaluate_rank_fact(pf, ref_map)
                type_stats["rank"]["total"] += 1
                if detail["is_correct"]:
                    type_stats["rank"]["correct"] += 1

            else:
                # 未知类型，默认按 value 处理
                detail = self._evaluate_value_fact(pf, ref_map)
                type_stats["value"]["total"] += 1
                if detail["is_correct"]:
                    type_stats["value"]["correct"] += 1

            if detail["is_correct"]:
                correct_count += 1

            details.append(detail)

        precision = correct_count / len(pred_facts)
        hallucination_count = len(pred_facts) - correct_count

        # 统计各类型参考事实数量
        ref_type_counts = {"value": 0, "range": 0, "rank": 0}
        for rf in ref_facts:
            t = rf.get("type", "value")
            if t in ref_type_counts:
                ref_type_counts[t] += 1

        return {
            "precision": precision,
            "correct_count": correct_count,
            "total_pred_facts": len(pred_facts),
            "total_ref_facts": len(ref_facts),
            "hallucination_count": hallucination_count,
            "by_type": type_stats,
            "ref_type_counts": ref_type_counts,
            "ref_facts": ref_facts,
            "pred_facts": pred_facts,
            "details": details
        }


# 便捷函数
_global_evaluator: Optional[FactScoreV3Evaluator] = None


def get_factscore_v3_evaluator() -> FactScoreV3Evaluator:
    """获取全局 FactScore v3 评估器实例"""
    global _global_evaluator
    if _global_evaluator is None:
        _global_evaluator = FactScoreV3Evaluator()
    return _global_evaluator
