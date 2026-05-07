"""
compute_r_fact_llm_v2.py — LLM 版 r_fact（v2: gemini-3-flash + 1-100 标度）

改进点:
  - 模型: gemini-3-flash-preview-nothinking（更强的事实核查能力）
  - 标度: 1-100 整数（减少 tie rate，提高区分度）
  - 其余与 v1 相同：独立评分，无 label leakage

使用方式:
  python compute_r_fact_llm_v2.py --test 5
  python compute_r_fact_llm_v2.py --max-workers 8
  python compute_r_fact_llm_v2.py --resume
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests

# ============================================================
# 常量
# ============================================================

API_KEY = "<YOUR_API_KEY>"
BASE_URL = "<YOUR_LLM_PROXY>/v1"
MODEL = "gemini-3-flash-preview-nothinking"

V2_DATA_DIR = Path("$DATA_ROOT/dpo-v2/data")
SOURCE_FACTS_PATH = V2_DATA_DIR / "source_facts.json"
DPO_DECOMPOSED_PATH = V2_DATA_DIR / "dpo_train_decomposed.jsonl"

V3_DATA_DIR = Path("$DATA_ROOT/dpo-v3/data")
DEFAULT_OUTPUT_PATH = V3_DATA_DIR / "r_fact_llm_v2.json"
DEFAULT_CHECKPOINT_PATH = V3_DATA_DIR / ".r_fact_llm_v2_checkpoint.json"

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2

# ============================================================
# Prompt — 单文本独立评估，模型不知道 chosen/rejected 身份
# ============================================================

JUDGE_PROMPT = """You are a financial data fact-checker. Your task is to evaluate how accurately a financial chart summary reports factual data, based on verified source data.

## Source Data (Ground Truth)
```json
{source_facts}
```

## Summary to Evaluate
{summary_text}

## Instructions

Score ONLY factual claims that can be directly verified against the source data above (e.g., specific values, dates, time ranges, min/max, percentage changes, trend directions).

**Do NOT penalize for:**
- Predictions or forward-looking statements ("may rise", "could drop to")
- Qualitative analysis or business interpretation
- Claims that cannot be verified from the source data (ignore, do not penalize)
- Writing style, completeness, or analytical depth

**Scoring scale (1-100):**
- 95-100: All verifiable factual claims are accurate, no errors found
- 85-94: 1 minor error (small rounding difference, slight date imprecision)
- 70-84: 2-3 minor factual errors or 1 significant error
- 50-69: Several factual errors; some key facts are wrong
- 30-49: Many factual errors; source data is substantially misrepresented
- 1-29: Pervasive factual errors; directly contradicts source data on most claims

**Respond in strict JSON only:**
{{
  "score": <integer 1-100>,
  "errors": ["<brief factual error, max 3 items>"],
  "reasoning": "<one sentence>"
}}"""


# ============================================================
# 辅助：压缩 source_facts 减少 prompt 长度
# ============================================================

def trim_source_facts(sf: dict, data_type: str) -> dict:
    """裁剪 source_facts，保留关键数值，压缩冗余细节。"""
    if data_type == "v4_csv":
        stats = sf.get("stats", {})
        trimmed_stats = {}
        for col, s in stats.items():
            trimmed_stats[col] = {
                "start_value": s.get("start_value"),
                "end_value": s.get("end_value"),
                "min": s.get("min"),
                "max": s.get("max"),
                "mean": round(s["mean"], 4) if "mean" in s else None,
                "std": round(s["std"], 4) if "std" in s else None,
                "overall_trend": s.get("overall_trend"),
                "max_drawdown": s.get("max_drawdown"),
            }
        return {
            "data_type": data_type,
            "time_range": sf.get("time_range"),
            "data_points": sf.get("data_points"),
            "columns": sf.get("columns"),
            "stats": trimmed_stats,
        }
    else:
        # v3_summary / v3_with_raw
        result = {
            "data_type": data_type,
            "time_range": sf.get("time_range"),
            "data_points": sf.get("data_points"),
            "stats": sf.get("stats"),
        }
        if "extremes" in sf:
            result["extremes"] = {}
            for col, ex in sf["extremes"].items():
                result["extremes"][col] = {
                    "global_max": ex.get("global_max"),
                    "global_min": ex.get("global_min"),
                }
        if "segments" in sf:
            result["segments"] = {}
            for col, segs in sf["segments"].items():
                if len(segs) <= 6:
                    result["segments"][col] = segs
                else:
                    result["segments"][col] = (
                        segs[:3]
                        + [{"note": f"... {len(segs)-6} segments omitted ..."}]
                        + segs[-3:]
                    )
        if "risk_metrics" in sf:
            result["risk_metrics"] = sf["risk_metrics"]
        return result


# ============================================================
# API 客户端 — 单文本独立评分
# ============================================================

class FactJudgeClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        })

    def score_single(self, source_facts: dict, summary_text: str, data_type: str) -> dict:
        """
        独立评分单段文本。返回 {"score": float, "errors": [...], "reasoning": str}
        模型不知道这段文本是 chosen 还是 rejected。
        """
        trimmed = trim_source_facts(source_facts, data_type)
        source_facts_str = json.dumps(trimmed, ensure_ascii=False, indent=2)
        prompt = JUDGE_PROMPT.format(
            source_facts=source_facts_str,
            summary_text=summary_text,
        )

        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.post(
                    f"{BASE_URL}/chat/completions",
                    json=payload,
                    timeout=120,
                )
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ValueError("Response truncated (finish_reason=length)")
                content = choice["message"]["content"]
                return self._parse_response(content)
            except (requests.exceptions.RequestException, KeyError, json.JSONDecodeError, ValueError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BASE_DELAY ** (attempt + 1)
                    print(f"  [重试 {attempt+1}/{MAX_RETRIES}] {type(e).__name__}: {e} — {wait}s 后重试")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"API 调用失败（已重试 {MAX_RETRIES} 次）: {e}")

    def _parse_response(self, content: str) -> dict:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
            data = json.loads(content)

        score = data.get("score", 5)
        score = max(1, min(100, float(score)))
        return {
            "score": score,
            "errors": data.get("errors", []),
            "reasoning": data.get("reasoning", ""),
        }


# ============================================================
# 核心处理
# ============================================================

def process_single(client: FactJudgeClient, idx: int, source_entry: dict, dpo_entry: dict) -> dict:
    """处理单条：Tier 1/2 各自独立评分；Tier 3 直接返回 delta=0。"""
    tier = source_entry["tier"]

    if tier == 3:
        return {
            "dpo_index": idx,
            "tier": 3,
            "r_fact_chosen": None,
            "r_fact_rejected": None,
            "delta_r_fact": 0.0,
            "skipped": True,
        }

    messages = dpo_entry["messages"]
    chosen_text = next(m["content"] for m in reversed(messages) if m["role"] == "assistant")
    rejected_text = dpo_entry["rejected_response"]
    source_facts = source_entry["source_facts"]
    data_type = source_entry.get("data_type", "v3_summary")

    # 两次独立调用，完全对称
    chosen_result = client.score_single(source_facts, chosen_text, data_type)
    rejected_result = client.score_single(source_facts, rejected_text, data_type)

    r_fact_chosen = round(chosen_result["score"] / 100.0, 4)
    r_fact_rejected = round(rejected_result["score"] / 100.0, 4)
    delta_r_fact = round(r_fact_chosen - r_fact_rejected, 4)

    return {
        "dpo_index": idx,
        "tier": tier,
        "r_fact_chosen": r_fact_chosen,
        "r_fact_rejected": r_fact_rejected,
        "delta_r_fact": delta_r_fact,
        "chosen_score_raw": chosen_result["score"],
        "rejected_score_raw": rejected_result["score"],
        "chosen_errors": chosen_result["errors"],
        "rejected_errors": rejected_result["errors"],
    }


# ============================================================
# 断点续传
# ============================================================

def load_checkpoint(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {r["dpo_index"]: r for r in data}
    return {}


def save_checkpoint(completed: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_results = sorted(completed.values(), key=lambda x: x["dpo_index"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted_results, f, ensure_ascii=False, indent=2)


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="LLM 版 r_fact 计算（独立评分）")
    parser.add_argument("--test", type=int, default=None, help="只处理前 N 条（测试用）")
    parser.add_argument("--max-workers", type=int, default=8, help="并发数（默认 8）")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--resume", action="store_true", help="从 checkpoint 续传")
    args = parser.parse_args()

    print(f"加载 source_facts: {SOURCE_FACTS_PATH}")
    with open(SOURCE_FACTS_PATH, encoding="utf-8") as f:
        source_facts_list = json.load(f)
    source_facts_map = {e["dpo_index"]: e for e in source_facts_list}
    print(f"  共 {len(source_facts_map)} 条 source_facts")

    print(f"加载 DPO 数据: {DPO_DECOMPOSED_PATH}")
    dpo_entries = []
    with open(DPO_DECOMPOSED_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                dpo_entries.append(json.loads(line))
    total = len(dpo_entries)
    print(f"  共 {total} 条 DPO 偏好对")

    indices = list(range(args.test if args.test else total))

    tier_counts = {}
    for i in indices:
        t = source_facts_map.get(i, {}).get("tier", 3)
        tier_counts[t] = tier_counts.get(t, 0) + 1
    api_calls = sum(v * 2 for k, v in tier_counts.items() if k != 3)
    print(f"  Tier 分布: {tier_counts}  预计 API 调用: {api_calls} 次（Tier1/2 每对 2 次独立调用）")

    completed = {}
    if args.resume:
        completed = load_checkpoint(args.checkpoint)
        if completed:
            print(f"  从 checkpoint 恢复: 已完成 {len(completed)} 条")

    todo_indices = [i for i in indices if i not in completed]
    print(f"  待处理: {len(todo_indices)} 条 (已完成 {len(indices) - len(todo_indices)} 条)")

    if not todo_indices:
        print("所有任务已完成！")
        save_final(completed, indices, args.output)
        return

    client = FactJudgeClient()
    results_lock = Lock()
    done_count = [len(completed)]
    start_time = time.time()
    errors = []
    SAVE_INTERVAL = 20

    def worker(idx):
        source_entry = source_facts_map.get(idx)
        dpo_entry = dpo_entries[idx]
        if source_entry is None:
            result = {
                "dpo_index": idx, "tier": 3,
                "r_fact_chosen": None, "r_fact_rejected": None,
                "delta_r_fact": 0.0, "skipped": True,
                "note": "source_facts not found",
            }
        else:
            result = process_single(client, idx, source_entry, dpo_entry)

        with results_lock:
            completed[idx] = result
            done_count[0] += 1
            elapsed = time.time() - start_time
            rate = done_count[0] / elapsed if elapsed > 0 else 0
            remaining = len(todo_indices) - (done_count[0] - (len(indices) - len(todo_indices)))
            eta_min = remaining / rate / 60 if rate > 0 else 0

            tier = result.get("tier", "?")
            if result.get("skipped"):
                tag = f"tier={tier} SKIP"
            else:
                tag = (f"tier={tier} "
                       f"chosen={result['r_fact_chosen']:.2f} "
                       f"rejected={result['r_fact_rejected']:.2f} "
                       f"Δ={result['delta_r_fact']:+.2f}")
            print(f"  [{done_count[0]}/{len(indices)}] idx={idx} {tag} ETA={eta_min:.0f}min")

            if done_count[0] % SAVE_INTERVAL == 0:
                save_checkpoint(completed, args.checkpoint)

        return result

    print(f"\n开始评估 (并发={args.max_workers}, 每对 2 次独立调用)...")
    print("=" * 70)

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(worker, idx): idx for idx in todo_indices}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"  [错误] idx={idx}: {e}")
                errors.append({"dpo_index": idx, "error": str(e)})

    save_checkpoint(completed, args.checkpoint)
    save_final(completed, indices, args.output)

    elapsed_total = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"完成！耗时 {elapsed_total:.1f}s ({elapsed_total/60:.1f}min)")
    print(f"  成功: {len(completed)} 条 | 失败: {len(errors)} 条")
    if errors:
        for e in errors[:10]:
            print(f"    idx={e['dpo_index']}: {e['error']}")

    print_summary(completed, indices)


def save_final(completed: dict, indices: list, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for idx in indices:
        if idx in completed:
            r = completed[idx]
            out = {
                "dpo_index": r["dpo_index"],
                "tier": r["tier"],
                "r_fact_chosen": r["r_fact_chosen"],
                "r_fact_rejected": r["r_fact_rejected"],
                "delta_r_fact": r["delta_r_fact"],
            }
            if r.get("skipped"):
                out["skipped"] = True
            if r.get("chosen_errors"):
                out["chosen_errors"] = r["chosen_errors"]
            if r.get("rejected_errors"):
                out["rejected_errors"] = r["rejected_errors"]
            results.append(out)
        else:
            results.append({
                "dpo_index": idx, "tier": None,
                "r_fact_chosen": None, "r_fact_rejected": None,
                "delta_r_fact": None, "error": "未完成",
            })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_path}")


def print_summary(completed: dict, indices: list):
    evaluated = [completed[i] for i in indices if i in completed and not completed[i].get("skipped")
                 and completed[i].get("delta_r_fact") is not None]
    skipped = [completed[i] for i in indices if i in completed and completed[i].get("skipped")]

    print(f"\n=== r_fact_llm_v2 汇总（gemini-3-flash, 1-100 标度）===")
    print(f"  Tier 1/2 已评估: {len(evaluated)} 条")
    print(f"  Tier 3 跳过:    {len(skipped)} 条 (delta=0)")

    if not evaluated:
        return

    chosen_scores = [r["r_fact_chosen"] for r in evaluated]
    rejected_scores = [r["r_fact_rejected"] for r in evaluated]
    deltas = [r["delta_r_fact"] for r in evaluated]

    print(f"\n  chosen r_fact:   均值={sum(chosen_scores)/len(chosen_scores):.4f}  "
          f"min={min(chosen_scores):.2f}  max={max(chosen_scores):.2f}")
    print(f"  rejected r_fact: 均值={sum(rejected_scores)/len(rejected_scores):.4f}  "
          f"min={min(rejected_scores):.2f}  max={max(rejected_scores):.2f}")

    pos = sum(1 for d in deltas if d > 0)
    zero = sum(1 for d in deltas if d == 0)
    neg = sum(1 for d in deltas if d < 0)
    print(f"\n  delta (chosen - rejected):")
    print(f"    均值={sum(deltas)/len(deltas):+.4f}  min={min(deltas):+.2f}  max={max(deltas):+.2f}")
    print(f"    chosen > rejected: {pos} ({pos/len(evaluated)*100:.1f}%)")
    print(f"    chosen = rejected: {zero} ({zero/len(evaluated)*100:.1f}%)")
    print(f"    chosen < rejected: {neg} ({neg/len(evaluated)*100:.1f}%)")

    from collections import Counter
    cnt = Counter(round(d, 1) for d in deltas)
    print(f"\n  delta 分布:")
    for k in sorted(cnt):
        bar = "█" * (cnt[k] // 10)
        print(f"    {k:+.1f}: {cnt[k]:4d} {bar}")

    t1 = [r for r in evaluated if r["tier"] == 1]
    t2 = [r for r in evaluated if r["tier"] == 2]
    if t1:
        d1 = [r["delta_r_fact"] for r in t1]
        print(f"\n  Tier1 ({len(t1)}条): delta均值={sum(d1)/len(d1):+.4f}  "
              f"chosen>rej={sum(1 for d in d1 if d>0)} ({sum(1 for d in d1 if d>0)/len(d1)*100:.0f}%)")
    if t2:
        d2 = [r["delta_r_fact"] for r in t2]
        print(f"  Tier2 ({len(t2)}条): delta均值={sum(d2)/len(d2):+.4f}  "
              f"chosen>rej={sum(1 for d in d2 if d>0)} ({sum(1 for d in d2 if d>0)/len(d2)*100:.0f}%)")


if __name__ == "__main__":
    main()
