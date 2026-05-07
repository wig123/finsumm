"""
veRL GRPO Reward Function — R_format only (GRPO-0 Smoke Test)

检查金融图表结构化总结是否包含四层结构 + 长度合理性。
不涉及 LLM Judge，纯规则，零延迟。

veRL reward 函数签名:
  compute_score(data_source, solution_str, ground_truth, extra_info=None) -> float
"""

import re


def compute_score(data_source, solution_str, ground_truth, extra_info=None):
    """
    veRL GRPO reward function — R_format only.

    四层结构检查:
      - 图表构成 / Chart Composition
      - 数据关系 / Data Relationships
      - 模式特征 / Pattern Features
      - 核心洞察 / Key Insights

    长度合理性:
      - [500, 3000] 字符: +0.1 bonus
      - > 5000 字符: -0.3 penalty

    Returns:
        float: reward score in [0.0, 1.0]
    """
    if not solution_str or not solution_str.strip():
        return 0.0

    # 四层结构检查 (中文/英文标题均可)
    sections = [
        r"图表构成|Chart Composition|Chart Components",
        r"数据关系|Data Relationships",
        r"模式特征|Pattern Features|Pattern Characteristics",
        r"核心洞察|Key Insights|Core Insights",
    ]

    present = 0
    for pattern in sections:
        if re.search(pattern, solution_str, re.IGNORECASE):
            present += 1

    score = present / len(sections)  # 0.0, 0.25, 0.5, 0.75, 1.0

    # 长度合理性
    text_len = len(solution_str)
    if 500 <= text_len <= 3000:
        score = min(score + 0.1, 1.0)
    elif text_len > 5000:
        score = max(score - 0.3, 0.0)

    return score


# ---------- 本地测试 ----------
if __name__ == "__main__":
    # 测试用例
    test_cases = [
        ("空输出", ""),
        ("只有格式标题", "[Chart Composition]\nA chart.\n[Data Relationships]\nSome data.\n[Pattern Features]\nA pattern.\n[Key Insights]\nAn insight."),
        ("中文四层 + 合理长度", "【图表构成】\n图表类型：折线图\n" + "内容" * 200 + "\n【数据关系】\n数据" * 50 + "\n【模式特征】\n模式" * 50 + "\n【核心洞察】\n结论" * 50),
        ("缺少两层", "[Chart Composition]\nA chart.\n[Key Insights]\nInsight."),
        ("过长输出", "[Chart Composition]\nA.\n[Data Relationships]\nB.\n[Pattern Features]\nC.\n[Key Insights]\nD.\n" + "padding " * 1000),
    ]

    for name, text in test_cases:
        score = compute_score("fin_chart_summary", text, "")
        print(f"  {name}: score={score:.2f}, len={len(text)}")
