#!/usr/bin/env python3
"""批量跑 L2 传统指标（BLEU/ROUGE/METEOR/CIDEr）"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evaluators.traditional import TraditionalMetricsEvaluator

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# 表中 11 个模型（排除 gpt-5-mini）的映射：显示名 → results 文件名
MODELS = {
    "gpt-5.4-mini":      "gpt-5_4-mini_l2_results.jsonl",
    "GLM-4.6V":          "GLM-4.6V_l2_results.jsonl",
    "Qwen3-VL-235B":     "Qwen3-VL-235B_l2_results.jsonl",
    "Gemini-2.5-Flash":  "Gemini-Flash_l2_results.jsonl",
    "GLM-4.6V-Flash":    "GLM-Flash-withGT_l2_results.jsonl",
    "SFT-ckpt640":       "SFT-ckpt640_l2_results.jsonl",
    "SFT-ckpt800":       "SFT-ckpt800_l2_results.jsonl",
    "gpt-5.4-nano":      "gpt-5_4-nano_l2_results.jsonl",
    "Qwen3-VL-30B":      "Qwen3-VL-30B_l2_results.jsonl",
    "gemini-flash-lite":  "gemini-2_5-flash-lite_l2_results.jsonl",
    "Base-8B":           "E-base-v2_l2_results.jsonl",
    "GPT-5.4":           "gpt-5_4_l2_results.jsonl",
    "Gemini-3.1-Pro":    "gemini-3.1-pro_l2_results.jsonl",
    "Kimi-k2.5":         "kimi-k2.5_l2_results.jsonl",
}


def load_results(filepath):
    """加载 JSONL，过滤空响应"""
    with open(filepath, encoding="utf-8") as f:
        samples = [json.loads(line) for line in f]
    valid = [s for s in samples if s.get("generated_text", "").strip()]
    return valid


def main():
    evaluator = TraditionalMetricsEvaluator()
    all_results = {}

    for model_name, filename in MODELS.items():
        path = os.path.join(OUTPUTS_DIR, filename)
        if not os.path.exists(path):
            print(f"❌ {model_name}: 文件不存在 {filename}")
            continue

        samples = load_results(path)
        predictions = [s["generated_text"] for s in samples]
        references = [s["ground_truth"] for s in samples]

        print(f"▶ {model_name} ({len(samples)} 有效样本)...", end=" ", flush=True)

        try:
            result = evaluator.evaluate(
                predictions, references,
                use_bertscore=False,  # 本地无 GPU，跳过
            )
            all_results[model_name] = {
                "valid_samples": len(samples),
                **result["overall"],
            }
            b4 = result["overall"].get("bleu_4", 0)
            r1 = result["overall"].get("rouge1", 0)
            rl = result["overall"].get("rougeL", 0)
            mt = result["overall"].get("meteor", 0)
            print(f"BLEU-4={b4:.4f}  ROUGE-1={r1:.4f}  ROUGE-L={rl:.4f}  METEOR={mt:.4f}")
        except Exception as e:
            print(f"失败: {e}")
            all_results[model_name] = {"error": str(e)}

    # 保存结果
    out_path = os.path.join(OUTPUTS_DIR, "traditional_metrics_L2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 结果已保存: {out_path}")


if __name__ == "__main__":
    main()
