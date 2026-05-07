#!/usr/bin/env python3
"""
统一候选评分脚本 — 给 Judge 看图片 + 源数据，独立评分每个候选。

输入:
  --candidates: candidates JSON (V1 candidates_2000.json 或 T0.6 t06_candidates_1280.json)
  --source-facts: source_facts.json (可选，有则用，无则仅靠图片)
  --image-base: 图片根目录

输出:
  scored_candidates.json: 每个候选的 fact_score (1-100) + 错误列表

用法:
  # 测试 2 个 item (12 次 API 调用)
  python score_candidates.py --candidates data/candidates.json --test 2

  # 全量跑
  python score_candidates.py --candidates data/candidates.json --max-workers 8

  # 断点续传
  python score_candidates.py --candidates data/candidates.json --resume
"""

import argparse
import base64
import json
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests

# ============================================================
# 配置
# ============================================================

API_KEY = os.getenv("APIYI_KEY", "<YOUR_API_KEY>")
BASE_URL = "<YOUR_LLM_PROXY>/v1"
DEFAULT_MODEL = "gemini-3-flash-preview-nothinking"

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2
_active_model = DEFAULT_MODEL

# ============================================================
# Judge Prompt — 看图片 + 看源数据 + 独立评分
# ============================================================

PROMPT_WITH_SOURCE = """You are a financial data fact-checker. Evaluate how accurately this chart summary describes the financial chart, using both the chart image and verified source data.

## Source Data (Ground Truth — verified numerical data)
```json
{source_facts}
```

## Summary to Evaluate
{summary}

## Instructions

**CRITICAL — Source Data Validation (do this FIRST):**
Compare the source data's time range, value ranges, and subject against the chart image. If ANY of these are true, COMPLETELY IGNORE the source data and evaluate ONLY against the chart image:
- Time periods differ by more than 1 year
- Value magnitudes differ by more than 50% (e.g., source max=9.5 but chart shows ~16)
- Subject/topic is clearly different
When ignoring source data, do NOT mention the mismatch in your errors — focus purely on the chart.

**Scoring rules:**
1. If source data is valid: verify numerical claims against source data (most reliable) AND visual claims against chart image.
2. If source data is ignored: verify all claims against the chart image only.
3. Score ONLY factual accuracy. Do NOT penalize for writing style, analytical depth, or completeness.
4. Claims that cannot be verified → ignore (do not penalize).

## Scoring Scale (1-100 integer)
- 95-100: All verifiable claims are accurate, no errors found
- 85-94: 1 minor error (small rounding, slight date imprecision)
- 70-84: 2-3 minor errors or 1 significant factual error
- 50-69: Several factual errors; some key data points are wrong
- 30-49: Many factual errors; substantially misrepresents the data
- 1-29: Pervasive factual errors; contradicts chart/source on most claims

## Output (strict JSON, no markdown)
{{"score": <integer 1-100>, "errors": ["<brief error description, max 5>"], "reasoning": "<one sentence>"}}"""

PROMPT_IMAGE_ONLY = """You are a financial data fact-checker. Evaluate how accurately this chart summary describes the financial chart, based on the chart image.

## Summary to Evaluate
{summary}

## Instructions
1. Compare the summary against the chart image.
2. Check: chart type, axis labels/ranges, data values, trend directions, extremes, comparisons.
3. Score ONLY factual accuracy. Do NOT penalize for writing style, analytical depth, or completeness.
4. If a claim cannot be verified from the image → ignore (do not penalize).

## Scoring Scale (1-100 integer)
- 95-100: All verifiable claims are accurate, no errors found
- 85-94: 1 minor error (small rounding, slight imprecision)
- 70-84: 2-3 minor errors or 1 significant factual error
- 50-69: Several factual errors; some key data points are wrong
- 30-49: Many factual errors; substantially misrepresents the chart
- 1-29: Pervasive factual errors; contradicts the chart on most claims

## Output (strict JSON, no markdown)
{{"score": <integer 1-100>, "errors": ["<brief error description, max 5>"], "reasoning": "<one sentence>"}}"""


# ============================================================
# 源数据压缩（复用 V3 逻辑）
# ============================================================

def trim_source_facts(sf: dict) -> dict:
    """压缩 source_facts，保留关键数值，减少 prompt 长度。"""
    data_type = sf.get("data_type", "")
    if data_type == "v4_csv":
        stats = sf.get("stats", {})
        trimmed = {}
        for col, s in stats.items():
            trimmed[col] = {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in s.items()
                if k in ("start_value", "end_value", "min", "max", "mean",
                         "std", "overall_trend", "max_drawdown")
                and v is not None
            }
        return {
            "data_type": data_type,
            "time_range": sf.get("time_range"),
            "data_points": sf.get("data_points"),
            "columns": sf.get("columns"),
            "stats": trimmed,
        }
    else:
        result = {
            "data_type": data_type,
            "time_range": sf.get("time_range"),
            "data_points": sf.get("data_points"),
            "stats": sf.get("stats"),
        }
        if "extremes" in sf:
            result["extremes"] = {
                col: {"global_max": ex.get("global_max"), "global_min": ex.get("global_min")}
                for col, ex in sf["extremes"].items()
            }
        if "segments" in sf:
            result["segments"] = {
                col: (segs[:3] + segs[-3:] if len(segs) > 6 else segs)
                for col, segs in sf["segments"].items()
            }
        if "risk_metrics" in sf:
            result["risk_metrics"] = sf["risk_metrics"]
        return result


# ============================================================
# API 调用
# ============================================================

_session_lock = Lock()
_sessions = {}


def get_session():
    tid = id(os.getpid())
    with _session_lock:
        if tid not in _sessions:
            s = requests.Session()
            s.headers.update({
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            })
            _sessions[tid] = s
        return _sessions[tid]


def encode_image(path: str) -> tuple:
    """返回 (base64_str, media_type)。"""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = Path(path).suffix.lower()
    media = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(ext, "image/png")
    return b64, media


def call_judge(summary: str, image_path: str, source_facts: dict | None) -> dict:
    """调用 Judge API，返回 {score, errors, reasoning}。"""
    if source_facts:
        trimmed = trim_source_facts(source_facts)
        prompt_text = PROMPT_WITH_SOURCE.format(
            source_facts=json.dumps(trimmed, ensure_ascii=False, indent=2),
            summary=summary,
        )
    else:
        prompt_text = PROMPT_IMAGE_ONLY.format(summary=summary)

    # 构建 message：图片 + 文本
    content_parts = []
    if image_path and Path(image_path).exists():
        b64, media = encode_image(image_path)
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media};base64,{b64}"},
        })
    content_parts.append({"type": "text", "text": prompt_text})

    payload = {
        "model": _active_model,
        "messages": [{"role": "user", "content": content_parts}],
        "temperature": 0.0,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }

    session = get_session()
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.post(f"{BASE_URL}/chat/completions", json=payload, timeout=120)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]

            # 解析 JSON（健壮处理各种格式）
            if "```" in text:
                text = re.sub(r"```(?:json)?", "", text).strip()
            parsed = json.loads(text)

            # 处理嵌套 JSON（有时模型返回 {"result": {...}} 等结构）
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}
            if "score" not in parsed:
                # 尝试找嵌套的 score
                for v in parsed.values():
                    if isinstance(v, dict) and "score" in v:
                        parsed = v
                        break

            raw_score = parsed.get("score", 50)
            score = max(1, min(100, int(float(str(raw_score)))))
            errors = parsed.get("errors", [])
            if not isinstance(errors, list):
                errors = [str(errors)]
            return {
                "score": score,
                "errors": errors[:5],
                "reasoning": str(parsed.get("reasoning", "")),
            }
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BASE_DELAY ** (attempt + 1)
                time.sleep(wait)
            else:
                return {"score": -1, "errors": [str(e)], "reasoning": "API_ERROR"}


# ============================================================
# 主流程
# ============================================================

def score_item(item: dict, image_base: str, facts_by_image: dict) -> dict:
    """评分单个 item 的所有候选。"""
    idx = item["index"]
    image_name = item["image"]
    image_path = str(Path(image_base) / image_name)
    candidates = item["candidates"]

    # 按图片文件名查找源数据（修复：不再用数字索引）
    img_key = Path(image_name).stem  # 去掉路径前缀和扩展名
    sf = facts_by_image.get(img_key)

    results = []
    for ci, cand in enumerate(candidates):
        if not cand:  # 空候选跳过
            results.append({"cand_index": ci, "score": 0, "errors": ["empty"], "reasoning": "empty candidate"})
            continue
        r = call_judge(cand, image_path, sf)
        r["cand_index"] = ci
        results.append(r)

    return {
        "item_index": idx,
        "image": image_name,
        "has_source_facts": sf is not None,
        "candidates": results,
    }


def main():
    parser = argparse.ArgumentParser(description="统一候选评分")
    parser.add_argument("--candidates", type=str, required=True, help="候选数据 JSON")
    parser.add_argument("--source-facts", type=str, default=None, help="source_facts.json (可选)")
    parser.add_argument("--image-base", type=str, default="$DATA_ROOT/sft/data",
                        help="图片根目录")
    parser.add_argument("--output", type=str, default=None, help="输出文件 (默认: 同目录 scored_xxx.json)")
    parser.add_argument("--max-workers", type=int, default=4, help="并发数")
    parser.add_argument("--test", type=int, default=None, help="仅测试 N 个 item")
    parser.add_argument("--resume", action="store_true", help="断点续传")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Judge 模型")
    args = parser.parse_args()

    global _active_model
    _active_model = args.model

    # 加载候选数据
    print(f"加载候选: {args.candidates}")
    with open(args.candidates) as f:
        all_items = json.load(f)
    print(f"  总 items: {len(all_items)}")

    if args.test:
        all_items = all_items[:args.test]
        print(f"  测试模式: 取前 {args.test} 个")

    # 加载源数据（可选）— 按图片文件名索引
    facts_by_image = {}
    if args.source_facts and Path(args.source_facts).exists():
        print(f"加载源数据: {args.source_facts}")
        with open(args.source_facts) as f:
            facts_list = json.load(f)

        # 需要 source_mapping.json 获取 dpo_index → image 映射
        source_mapping_path = Path(args.source_facts).parent / "source_mapping.json"
        if source_mapping_path.exists():
            with open(source_mapping_path) as f:
                source_mapping = json.load(f)
            # dpo_index → image
            dpo_to_image = {item["dpo_index"]: item.get("image", "") for item in source_mapping}
        else:
            print(f"  ⚠️ 未找到 source_mapping.json，尝试从 source_facts 中提取 image 字段")
            dpo_to_image = {}

        # 构建 image_stem → source_facts 的映射
        facts_by_dpo = {}
        for item in facts_list:
            dpo_idx = item.get("dpo_index", item.get("index"))
            if dpo_idx is not None and item.get("source_facts"):
                facts_by_dpo[dpo_idx] = item["source_facts"]

        for dpo_idx, sf in facts_by_dpo.items():
            img = dpo_to_image.get(dpo_idx, "")
            if img:
                img_key = Path(img).stem
                facts_by_image[img_key] = sf

        print(f"  有源数据的图片: {len(facts_by_image)}")
        # 验证抽样
        sample_keys = list(facts_by_image.keys())[:3]
        for k in sample_keys:
            sf = facts_by_image[k]
            tr = sf.get("time_range", sf.get("data_points", "?"))
            print(f"    {k} → {sf.get('data_type', '?')}, time_range={tr}")
    else:
        print("  无源数据，仅靠图片评分")

    # 输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        stem = Path(args.candidates).stem
        output_path = Path(args.candidates).parent / f"scored_{stem}.json"

    # 断点续传
    completed = {}
    checkpoint_path = output_path.with_suffix(".checkpoint.json")
    if args.resume and checkpoint_path.exists():
        with open(checkpoint_path) as f:
            completed_list = json.load(f)
        completed = {r["item_index"]: r for r in completed_list}
        print(f"  断点续传: 已完成 {len(completed)} 个")

    pending = [item for item in all_items if item["index"] not in completed]
    print(f"  待处理: {len(pending)} 个 ({len(pending) * 6} 次 API 调用)")
    print(f"  并发: {args.max_workers}")
    print(f"  模型: {_active_model}")
    print()

    # 开始评分
    results = list(completed.values())
    save_lock = Lock()
    done_count = len(completed)
    total = len(all_items)

    def process_and_save(item):
        nonlocal done_count
        r = score_item(item, args.image_base, facts_by_image)

        with save_lock:
            results.append(r)
            done_count += 1

            # 每 10 个保存 checkpoint
            if done_count % 10 == 0:
                with open(checkpoint_path, "w") as f:
                    json.dump(results, f, ensure_ascii=False)
                scores = [c["score"] for c in r["candidates"] if c["score"] > 0]
                avg = sum(scores) / len(scores) if scores else 0
                print(f"  [{done_count}/{total}] item={r['item_index']}, "
                      f"avg_score={avg:.0f}, has_sf={r['has_source_facts']}")

        return r

    if args.max_workers <= 1:
        for item in pending:
            process_and_save(item)
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
            futures = {pool.submit(process_and_save, item): item for item in pending}
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    item = futures[future]
                    print(f"  ⚠️ item {item['index']} 失败: {e}")

    # 保存最终结果
    results.sort(key=lambda r: r["item_index"])
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 清理 checkpoint
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    # 统计
    print("\n" + "=" * 60)
    print(f"完成！已保存: {output_path}")
    print(f"总 items: {len(results)}")

    all_scores = []
    with_sf = without_sf = 0
    for r in results:
        if r["has_source_facts"]:
            with_sf += 1
        else:
            without_sf += 1
        for c in r["candidates"]:
            if c["score"] > 0:
                all_scores.append(c["score"])

    print(f"有源数据: {with_sf}, 无源数据: {without_sf}")
    if all_scores:
        print(f"分数分布: mean={sum(all_scores)/len(all_scores):.1f}, "
              f"min={min(all_scores)}, max={max(all_scores)}")
        # 分位数
        sorted_s = sorted(all_scores)
        n = len(sorted_s)
        for p in [10, 25, 50, 75, 90]:
            print(f"  P{p}: {sorted_s[int(n * p / 100)]}")
    print("=" * 60)


if __name__ == "__main__":
    main()
