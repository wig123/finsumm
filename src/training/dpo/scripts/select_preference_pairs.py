#!/usr/bin/env python3
"""
DPO 偏好对选择脚本

从 6 个候选中选择 chosen 和 rejected (hard-negative)
使用 gemini-3-flash-preview-nothinking 作为 Judge
"""

import os
import json
import base64
import time
import argparse
import threading
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import requests


# ============== Prompt ==============

PREFERENCE_JUDGE_PROMPT = """# 任务：DPO 偏好对选择

你是金融图表分析专家。从 6 个候选摘要中选出：
1. **chosen**: 最准确、最完整的摘要
2. **rejected**: 看起来专业但存在关键事实错误的摘要（Hard-negative）

## 输入

### 参考标准摘要 (Ground Truth)
```
{ground_truth}
```

### 候选摘要
[0] {candidate_0}

[1] {candidate_1}

[2] {candidate_2}

[3] {candidate_3}

[4] {candidate_4}

[5] {candidate_5}

## 评判维度（按优先级）

### 1. 忠实度 (Faithfulness) - 权重 35%
摘要是否准确反映图表数据？

| 等级 | 标准 |
|------|------|
| 5 | 所有数值、趋势、对比都正确（误差 ≤3%），无幻觉 |
| 4 | 1-2 个数值有小误差（3-5%），无明显幻觉 |
| 3 | 部分数值误差（5-10%）或 1 个小幻觉，核心趋势正确 |
| 2 | 多个显著错误或幻觉，部分趋势被错误表述 |
| 1 | 错误普遍，严重幻觉，根本性曲解图表 |

### 2. 覆盖度 (Completeness) - 权重 30%
摘要是否覆盖了图表的关键信息？

| 等级 | 标准 |
|------|------|
| 5 | 覆盖所有关键数据点、主要趋势、极值、重要对比 |
| 4 | 覆盖大部分关键信息，遗漏 1 个次要数据点 |
| 3 | 覆盖核心趋势和部分关键值，遗漏 2-3 个重要点 |
| 2 | 仅覆盖部分信息，遗漏主要趋势或关键极值 |
| 1 | 严重不完整，遗漏大部分重要信息 |

### 3. 分析深度 (Analysis) - 权重 25%
摘要是否提供了超越数据描述的有意义洞察？

| 等级 | 标准 |
|------|------|
| 5 | 提供深刻分析，包含业务含义、风险因素、可操作阈值 |
| 4 | 分析良好，含义清晰，风险讨论略有不足 |
| 3 | 有基础分析，洞察较为泛泛 |
| 2 | 分析极少，主要是复述数字 |
| 1 | 无有意义分析，纯粹数据堆砌 |

### 4. 简洁性 (Conciseness) - 权重 10%
摘要是否简洁无冗余？

| 等级 | 标准 |
|------|------|
| 5 | 高度精炼，每句话都有价值，无冗余 |
| 4 | 基本简洁，有 1-2 处重复 |
| 3 | 长度可接受，有些冗长或重复 |
| 2 | 明显冗长，多处重复陈述 |
| 1 | 极度冗长或填充大量无关内容 |

## 选择逻辑

### chosen 选择
综合四维度，选择**总体最优**的候选。忠实度是首要考量。

### rejected 选择 (Hard-negative)
在剩余候选中，优先选择**看起来专业但有关键事实错误**的：

| 错误类型 | 示例 |
|----------|------|
| 趋势方向错 | ground_truth 显示"上升"，候选写"下降" |
| 极值位置错 | 最高点在 2023-07，候选写 2024-02 |
| 极值幅度错 | 最大值 8.5，候选写 12.3 |
| 变点遗漏 | 遗漏关键转折点 |
| 波动判断错 | 高波动期写成"平稳" |
| 回撤幅度错 | 最大回撤 -40%，候选写 -15% |

**降级**：如果所有候选都无明显事实错误，选择质量最差的，标记为 `quality_gap`。

## 输出格式 (严格 JSON)

```json
{{
  "chosen_idx": <0-5>,
  "rejected_idx": <0-5>,
  "rejection_type": "hard_negative" | "quality_gap",
  "factual_errors": ["错误描述1", "错误描述2"],
  "reasoning": "选择理由（1-2句）"
}}
```"""


# ============== API Client ==============

class GeminiClient:
    """Gemini API 客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "<YOUR_LLM_PROXY>/v1",
        model: str = "gemini-3-flash-preview-nothinking",
        max_retries: int = 3,
        timeout: int = 120
    ):
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

    def _encode_image(self, image_path: str) -> str:
        """将图片编码为 base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def chat(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096
    ) -> Dict:
        """调用 API"""
        messages = []

        if image_path and Path(image_path).exists():
            image_b64 = self._encode_image(image_path)
            img_format = Path(image_path).suffix.lower()
            media_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
            }.get(img_format, 'image/png')

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
                return {"content": content, "usage": result.get("usage", {})}

            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"\nAPI 调用失败，{wait_time}秒后重试... ({attempt + 1}/{self.max_retries}): {e}")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"API 调用失败: {e}")

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


# ============== Preference Selector ==============

class PreferenceSelector:
    """偏好对选择器"""

    def __init__(
        self,
        image_base_path: str,
        concurrency: int = 8,
        model: str = "gemini-3-flash-preview-nothinking",
        api_key: Optional[str] = None,
        base_url: str = "<YOUR_LLM_PROXY>/v1"
    ):
        self.image_base_path = Path(image_base_path)
        self.concurrency = concurrency

        # 为每个线程创建独立的客户端
        self.clients = [
            GeminiClient(
                api_key=api_key,
                base_url=base_url,
                model=model
            )
            for _ in range(concurrency)
        ]

        self.progress_lock = threading.Lock()

    def select_preference(
        self,
        sample: Dict,
        worker_id: int,
        progress_file: str
    ) -> Dict:
        """为单个样本选择偏好对"""
        sample_idx = sample.get("index", -1)
        image_path = self.image_base_path / sample["image"]
        ground_truth = sample["ground_truth"]
        candidates = sample["candidates"]

        # 构建 prompt
        prompt = PREFERENCE_JUDGE_PROMPT.format(
            ground_truth=ground_truth,
            candidate_0=candidates[0],
            candidate_1=candidates[1],
            candidate_2=candidates[2],
            candidate_3=candidates[3],
            candidate_4=candidates[4],
            candidate_5=candidates[5],
        )

        client = self.clients[worker_id]

        result = {
            "index": sample_idx,
            "image": sample["image"],
            "_source": sample.get("_source", ""),
        }

        try:
            response = client.chat(
                prompt=prompt,
                image_path=str(image_path),
                temperature=0.0
            )

            parsed = client.extract_json(response)

            result["chosen_idx"] = parsed.get("chosen_idx")
            result["rejected_idx"] = parsed.get("rejected_idx")
            result["rejection_type"] = parsed.get("rejection_type", "unknown")
            result["factual_errors"] = parsed.get("factual_errors", [])
            result["reasoning"] = parsed.get("reasoning", "")
            result["status"] = "success"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        # 保存进度
        with self.progress_lock:
            with open(progress_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

        return result

    def select_batch(
        self,
        samples: List[Dict],
        progress_file: str,
        completed: Dict[int, Dict]
    ) -> List[Dict]:
        """批量选择偏好对"""
        results = list(completed.values())
        pending = [s for s in samples if s.get("index", -1) not in completed]

        if not pending:
            print("✓ 所有样本已完成")
            return results

        print(f"📊 待处理样本: {len(pending)}")

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {
                executor.submit(
                    self.select_preference,
                    sample,
                    i % self.concurrency,
                    progress_file
                ): sample
                for i, sample in enumerate(pending)
            }

            for future in tqdm(as_completed(futures), total=len(futures), desc="选择偏好对"):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    sample = futures[future]
                    print(f"\n⚠️ 处理失败 ({sample.get('index', '')}): {e}")
                    results.append({
                        "index": sample.get("index", -1),
                        "status": "error",
                        "error": str(e)
                    })

        return results


def load_progress(progress_file: str) -> Dict[int, Dict]:
    """加载进度"""
    completed = {}
    if Path(progress_file).exists():
        with open(progress_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    idx = item.get("index", -1)
                    if idx >= 0:
                        completed[idx] = item
                except:
                    pass
    return completed


def main():
    parser = argparse.ArgumentParser(description="DPO 偏好对选择")
    parser.add_argument("--input", "-i", type=str, default="data/sampled/sampled_1000.json", help="输入文件")
    parser.add_argument("--output", "-o", type=str, default="data/preference/preference_pairs.json", help="输出文件")
    parser.add_argument("--image-base", type=str, default="$DATA_ROOT/sft/data", help="图片基础路径")
    parser.add_argument("--concurrency", "-c", type=int, default=8, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="限制处理数量")
    parser.add_argument("--model", type=str, default="gemini-3-flash-preview-nothinking", help="模型名称")

    args = parser.parse_args()

    # 路径处理
    base_dir = Path(__file__).parent.parent
    input_path = base_dir / args.input
    output_path = base_dir / args.output
    progress_file = str(output_path).replace(".json", ".progress.jsonl")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("📊 DPO 偏好对选择")
    print("=" * 70)
    print(f"📁 输入文件: {input_path}")
    print(f"📁 输出文件: {output_path}")
    print(f"🖼️  图片路径: {args.image_base}")
    print(f"🔄 并发数: {args.concurrency}")
    print(f"🤖 模型: {args.model}")
    print()

    # 加载数据
    with open(input_path, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    if args.limit:
        samples = samples[:args.limit]

    print(f"✓ 加载了 {len(samples)} 个样本\n")

    # 加载进度
    completed = load_progress(progress_file)
    print(f"📂 断点恢复: 已完成 {len(completed)} 个样本\n")

    # 选择偏好对
    selector = PreferenceSelector(
        image_base_path=args.image_base,
        concurrency=args.concurrency,
        model=args.model
    )

    results = selector.select_batch(samples, progress_file, completed)

    # 统计结果
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = sum(1 for r in results if r.get("status") == "error")
    hard_negative_count = sum(1 for r in results if r.get("rejection_type") == "hard_negative")
    quality_gap_count = sum(1 for r in results if r.get("rejection_type") == "quality_gap")

    print("\n" + "=" * 70)
    print("📊 结果统计")
    print("=" * 70)
    print(f"  成功: {success_count}")
    print(f"  失败: {error_count}")
    print(f"  Hard-negative: {hard_negative_count}")
    print(f"  Quality-gap: {quality_gap_count}")

    # 保存结果
    results_sorted = sorted(results, key=lambda x: x.get("index", -1))

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results_sorted, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 结果已保存: {output_path}")


if __name__ == "__main__":
    main()
