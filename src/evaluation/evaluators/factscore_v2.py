"""
FinMME-FactScore v2 评估器
使用 Claude Sonnet 4.5 一次调用完成：抽取 + 匹配 + 图表验证
数值比对使用规则计算，更稳定可靠
"""

import json
import base64
import time
from typing import Dict, List, Optional, Union
from pathlib import Path
import requests


class FactScoreV2Evaluator:
    """FactScore v2 - GPT-5.1 一次调用 + 规则数值比对"""

    RELATIVE_TOLERANCE = 0.03  # 3% 容差

    PROMPT = """你是金融图表分析专家。请完成以下任务：

【参考文本】
{reference}

【预测文本】
{prediction}

【任务】
1. 从参考文本中抽取所有数值关系 (ref_facts)
2. 从预测文本中抽取所有数值关系 (pred_facts)
3. 对每个 pred_fact：
   - 找语义上对应的 ref_fact（描述同一指标），填入 ref_id
   - 看图读取该指标的实际值，填入 chart

【输出格式】严格 JSON：
{{
  "ref_facts": [
    {{"id": 1, "entity": "价格最高点", "value": 170}},
    {{"id": 2, "entity": "价格最低点", "value": 135}}
  ],
  "pred_facts": [
    {{"id": 1, "entity": "价格峰值", "value": 168, "ref_id": 1, "chart": 170}},
    {{"id": 2, "entity": "某数据", "value": 200, "ref_id": null, "chart": null}}
  ]
}}

【规则】
- value 必须是数字
- ref_id: 语义匹配的 ref_fact id，无匹配则 null
- chart: 从图表中读取的对应数值，无法读取则 null
- entity: 简短描述（如"营收Q1"、"增长率"）
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
        """调用 Claude Sonnet 4.5 API"""
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
                    raise RuntimeError(f"GPT-5.1 API 调用失败: {e}")

    def _check_match(self, pred_value: float, target_value: float) -> bool:
        """规则计算：检查数值是否在容差范围内"""
        if target_value == 0:
            return abs(pred_value) < 0.001
        relative_error = abs(pred_value - target_value) / abs(target_value)
        return relative_error <= self.relative_tolerance

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
        prompt = self.PROMPT.format(
            reference=reference,
            prediction=prediction
        )

        # 一次调用 GPT-5.1
        result = self._call_api(prompt, image_path)

        ref_facts = result.get("ref_facts", [])
        pred_facts = result.get("pred_facts", [])

        if not pred_facts:
            return {
                "precision": 0.0,
                "correct_count": 0,
                "total_pred_facts": 0,
                "total_ref_facts": len(ref_facts),
                "ref_match_count": 0,
                "chart_support_count": 0,
                "hallucination_count": 0,
                "ref_facts": ref_facts,
                "pred_facts": pred_facts,
                "details": []
            }

        # 构建 ref_facts 映射
        ref_map = {f["id"]: f for f in ref_facts}

        # 规则计算
        correct_count = 0
        ref_match_count = 0
        chart_support_count = 0
        details = []

        for pf in pred_facts:
            pred_id = pf["id"]
            pred_value = pf.get("value")
            ref_id = pf.get("ref_id")
            chart_value = pf.get("chart")

            is_correct = False
            match_type = None

            # 检查 ref 匹配
            if ref_id is not None and ref_id in ref_map:
                ref_value = ref_map[ref_id].get("value")
                if ref_value is not None and pred_value is not None:
                    if self._check_match(pred_value, ref_value):
                        is_correct = True
                        match_type = "ref_match"
                        ref_match_count += 1

            # 如果 ref 没匹配上，检查图表支持
            if not is_correct and chart_value is not None and pred_value is not None:
                if self._check_match(pred_value, chart_value):
                    is_correct = True
                    match_type = "chart_support"
                    chart_support_count += 1

            if is_correct:
                correct_count += 1

            details.append({
                "pred_id": pred_id,
                "entity": pf.get("entity", ""),
                "pred_value": pred_value,
                "ref_id": ref_id,
                "ref_value": ref_map.get(ref_id, {}).get("value") if ref_id else None,
                "chart_value": chart_value,
                "is_correct": is_correct,
                "match_type": match_type
            })

        precision = correct_count / len(pred_facts)
        hallucination_count = len(pred_facts) - correct_count

        return {
            "precision": precision,
            "correct_count": correct_count,
            "total_pred_facts": len(pred_facts),
            "total_ref_facts": len(ref_facts),
            "ref_match_count": ref_match_count,
            "chart_support_count": chart_support_count,
            "hallucination_count": hallucination_count,
            "ref_facts": ref_facts,
            "pred_facts": pred_facts,
            "details": details
        }


# 便捷函数
_global_evaluator: Optional[FactScoreV2Evaluator] = None


def get_factscore_v2_evaluator() -> FactScoreV2Evaluator:
    """获取全局 FactScore v2 评估器实例"""
    global _global_evaluator
    if _global_evaluator is None:
        _global_evaluator = FactScoreV2Evaluator()
    return _global_evaluator
