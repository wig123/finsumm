"""
generate_fcpo_data.py — V3 FCPO 训练数据生成

读取：
  - dpo_train_decomposed.jsonl（DPO 偏好对结构）
  - r_fact_llm.json（独立评分版 delta_r_fact）

生成 LLaMA-Factory 兼容的 DPO 训练数据，γ=1/2/4 三组：
  - fcpo_gamma1.jsonl: margin_i = max(0, 1 × delta_r_fact_i)
  - fcpo_gamma2.jsonl: margin_i = max(0, 2 × delta_r_fact_i)
  - fcpo_gamma4.jsonl: margin_i = max(0, 4 × delta_r_fact_i)
"""

import json
import statistics
from pathlib import Path

V2_DATA = Path("$DATA_ROOT/dpo-v2/data")
V3_DATA = Path("$DATA_ROOT/dpo-v3/data")

DPO_INPUT = V2_DATA / "dpo_train_decomposed.jsonl"
R_FACT_LLM = V3_DATA / "r_fact_llm.json"

GAMMAS = [1, 2, 4]


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def strip_to_lf_format(item, margin: float) -> dict:
    """输出 LLaMA-Factory DPO 格式：messages + rejected_response + images + margin"""
    return {
        "messages": item["messages"],
        "rejected_response": item["rejected_response"],
        "images": item["images"],
        "margin": round(margin, 4),
    }


def main():
    # 加载 DPO 基础数据
    print(f"加载 DPO 数据: {DPO_INPUT}")
    dpo_data = load_jsonl(DPO_INPUT)
    print(f"  {len(dpo_data)} 条")

    # 加载 LLM r_fact
    print(f"加载 r_fact_llm: {R_FACT_LLM}")
    with open(R_FACT_LLM) as f:
        r_fact_list = json.load(f)
    r_fact_map = {r["dpo_index"]: r for r in r_fact_list}
    print(f"  {len(r_fact_map)} 条")

    # 合并 delta_r_fact
    deltas = []
    for i, item in enumerate(dpo_data):
        rf = r_fact_map.get(i, {})
        delta = rf.get("delta_r_fact")
        if delta is None or rf.get("skipped") or rf.get("error"):
            delta = 0.0
        deltas.append(delta)

    nonzero_deltas = [d for d in deltas if abs(d) > 0.001]
    pos_deltas = [d for d in deltas if d > 0.001]
    neg_deltas = [d for d in deltas if d < -0.001]
    print(f"\n  delta 统计:")
    print(f"    非零: {len(nonzero_deltas)} ({len(nonzero_deltas)/len(deltas)*100:.1f}%)")
    print(f"    正:   {len(pos_deltas)} ({len(pos_deltas)/len(deltas)*100:.1f}%)")
    print(f"    负:   {len(neg_deltas)} ({len(neg_deltas)/len(deltas)*100:.1f}%)")
    print(f"    零:   {len(deltas)-len(nonzero_deltas)} ({(len(deltas)-len(nonzero_deltas))/len(deltas)*100:.1f}%)")
    if nonzero_deltas:
        print(f"    |非零| 均值: {statistics.mean([abs(d) for d in nonzero_deltas]):.4f}")

    # 生成每个 γ 的数据
    V3_DATA.mkdir(parents=True, exist_ok=True)

    for gamma in GAMMAS:
        print(f"\n=== γ={gamma} ===")
        margins = []
        result = []
        for i, item in enumerate(dpo_data):
            m = max(0.0, gamma * deltas[i])
            margins.append(m)
            result.append(strip_to_lf_format(item, m))

        pos_m = [m for m in margins if m > 0]
        zero_m = sum(1 for m in margins if m == 0)
        print(f"  正 margin: {len(pos_m)} ({len(pos_m)/len(margins)*100:.1f}%)")
        print(f"  零 margin: {zero_m} ({zero_m/len(margins)*100:.1f}%)")
        if pos_m:
            print(f"  正 margin: 均值={statistics.mean(pos_m):.4f}  "
                  f"min={min(pos_m):.4f}  max={max(pos_m):.4f}")
        print(f"  全局 margin 均值: {statistics.mean(margins):.4f}")

        out_path = V3_DATA / f"fcpo_gamma{gamma}.jsonl"
        with open(out_path, "w") as f:
            for item in result:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  -> {out_path.name}")

    print("\n完成！")


if __name__ == "__main__":
    main()
