#!/usr/bin/env python3
"""
重建训练数据集脚本 - 全部从源目录重新生成（统一提示词）

数据源:
1. prog_ (1000张): chart-synthesis-v3/prog_2000/summaries
2. syn_ (967张): chart-synthesis-v3/production_4000/summaries
3. syn_v2_ (1000张): chart-synthesis-v3/production_4000_v2/summaries
4. syn_v4_ (1000张): chart-synthesis-v4/output/batch_2000
5. syn_v4f_ (过滤后): chart-synthesis-v4/output/batch_1000_final
6. mc_ (不变): data/fin-chart
7. finmme_ (不变): data/finmme
"""

import json
import os
import shutil
import random
from pathlib import Path
from typing import List, Dict, Set, Tuple
from tqdm import tqdm

# ============== 配置 ==============

RANDOM_SEED = 42
TARGET_COUNT = 1000
TRAIN_RATIO = 0.8

# 路径配置
DATA_DIR = Path("$DATA_ROOT/sft/data")
IMAGES_DIR = DATA_DIR / "images"

# V3 源目录
V3_BASE = Path("<WORKSPACE>/合成图表/chart-synthesis-v3")
PROG_SOURCE = V3_BASE / "prog_2000/summaries"
SYN_SOURCE = V3_BASE / "production_4000/summaries"  # syn_ 的源目录
SYN_V2_SOURCE = V3_BASE / "production_4000_v2/summaries"

# V4 源目录
V4_BASE = Path("<WORKSPACE>/合成图表/chart-synthesis-v4/output")
BATCH_2000 = V4_BASE / "batch_2000"
BATCH_1000_FINAL = V4_BASE / "batch_1000_final"

# 排除目录
EXCLUDE_DIRS = [
    Path("$DATA_ROOT/benchmark/data/sync_300_cn"),
    Path("$DATA_ROOT/benchmark/data/sync_300_en"),
]

# Prompts - 与评估时使用的提示词保持一致
SYSTEM_PROMPT_ZH = """你是一位严谨的、专注于金融领域的图表分析专家。你的唯一任务是接收一张金融图表，并严格遵循一个由四部分组成的结构，生成一份客观、独立的分析报告。

**核心规则:**
1. **遵循结构:** 你的报告必须严格包含【图表构成】、【数据关系】、【模式特征】、和【核心洞察】这四个部分的标题。
2. **信息封闭原则:** 你的所有分析，尤其是【核心洞察】部分，必须完全且仅来源于图表本身的视觉信息。严禁引入任何图表之外的市场新闻、宏观事件、公司背景或进行预测。
3. **纯净输出:** 你的回答必须是纯文本，直接从【图表构成】开始，报告结束后不添加任何附言或总结。
---

**请严格按照以下四层结构，并坚守信息封闭原则，分析你看到的金融图表：**

**【图表构成】**
- **任务:** 简洁描述图表的基础构成元素。
- **内容:** 图表类型、标题、坐标轴/维度的范围和标签（如有）、图例（颜色/样式编码）。只描述关键元素，无需穷尽所有细节。

**【数据关系】**
- **任务:** 提取图表中最关键的、可量化的数据事实。
- **内容:**
  - 关键数值及其位置（如：极值、关键点位、重要时点的数据）
  - 主要的数量关系（如：变动幅度、占比、差距、相关系数、分布范围）
  - 数据点之间的简单对比（如：A与B的关系、前后的变化）
- **要求:**
  - 只列出对理解图表重要的数据关系
  - 确保**数值准确**，忠实于图表

**【模式特征】**
- **任务:** 用几句话纯粹描述数据的形态特征，不做任何业务解读。
- **内容:**
  - 整体形态（如时序图：趋势方向、波动幅度、周期性；如分布图：集中度、对称性、聚类特征；如关系图：相关性分布、线性程度）
  - 结构特点（如：均衡/失衡、连续/跳跃、单一主导/多元分散）
  - 明显的异常、拐点或例外（如有）
- **要求:**
  - 这是纯粹的"形态层"，只描述数据的视觉模式
  - 避免重复【数据关系】中的具体数值
  - 严禁使用业务解读词汇（如"健康""疲软""风险""优势"等）
  - 用中性的形态词汇描述"看到的模式是什么"，而非"这意味着什么"

**【核心洞察】**
- **任务:** 基于前面的形态特征，提炼业务层面的结论和影响。这是"业务解读层"，而非"形态描述层"。
- **内容结构（严格遵循）:**
  ```
  核心结论：（最重要的业务判断，≤30字）

  业务含义：
  - 含义1（这个模式说明什么业务状况/问题/优势？≤20字）
  - 含义2（对哪个环节/指标/能力有什么影响？≤20字）
  - 含义3（如有，进一步的业务推论，≤20字）

  风险关注：
  - 风险点1（具体阈值+可能后果，≤25字）
  - 风险点2（如有，具体阈值+可能后果，≤25字）
  ```
- **要求:**
  - 总字数控制在250字左右，使用直白的商业语言
  - **严禁重复【模式特征】中的形态描述**（如"上升""背离""波动"等形态词汇）
  - **"业务含义"必须是业务层面的解读**，回答以下问题之一：
    - 这个模式说明了什么状况？（如：盈利能力、市场情绪、风险水平、配置效率、相关性强度）
    - 对什么有什么影响？（如：对决策的影响、对风险敞口的影响、对资产配置的含义、对流动性的影响）
    - 反映了什么特征？（如：稳定性、依赖性、集中度、敏感性、对称性、周期性）
  - **"风险关注"必须包含具体信息：**
    - 明确的数字阈值或临界点
    - 直白的可能后果或影响
    - 避免抽象或模糊的表述
  - 严禁引用任何未在图表中出现的信息"""

SYSTEM_PROMPT_EN = """You are a rigorous chart analysis expert specializing in the financial domain. Your sole task is to receive a financial chart and generate an objective, independent analysis report strictly following a four-part structure.

**Core Rules:**
1. **Follow the Structure:** Your report must strictly include these four section headers: [Chart Composition], [Data Relationships], [Pattern Characteristics], and [Core Insights].
2. **Information Closure Principle:** All your analysis, especially the [Core Insights] section, must be derived entirely and solely from the visual information in the chart itself. It is strictly forbidden to introduce any market news, macroeconomic events, company backgrounds, or predictions from outside the chart.
3. **Clean Output:** Your response must be plain text, starting directly from [Chart Composition], with no postscript or summary added after the report ends.
---

**Please strictly follow the four-layer structure below, and adhere to the information closure principle, to analyze the financial chart you see:**

**[Chart Composition]**
- **Task:** Concisely describe the basic compositional elements of the chart.
- **Content:** Chart type, title, axis/dimension ranges and labels (if any), legend (color/style encoding). Only describe key elements; no need to exhaust all details.

**[Data Relationships]**
- **Task:** Extract the most critical, quantifiable data facts from the chart.
- **Content:**
  - Key values and their positions (e.g., extremes, key levels, data at important time points)
  - Main quantitative relationships (e.g., magnitude of change, proportions, gaps, correlation coefficients, distribution ranges)
  - Simple comparisons between data points (e.g., relationship between A and B, before and after changes)
- **Requirements:**
  - Only list data relationships important for understanding the chart
  - Ensure **numerical accuracy**, faithful to the chart

**[Pattern Characteristics]**
- **Task:** Use a few sentences to purely describe the morphological characteristics of the data, without any business interpretation.
- **Content:**
  - Overall shape (e.g., for time series: trend direction, volatility amplitude, periodicity; for distribution charts: concentration, symmetry, clustering characteristics; for relationship charts: correlation distribution, degree of linearity)
  - Structural features (e.g., balanced/imbalanced, continuous/discontinuous, single dominant/multi-diversified)
  - Obvious anomalies, inflection points, or exceptions (if any)
- **Requirements:**
  - This is purely the "morphological layer," only describing visual patterns in the data
  - Avoid repeating specific values from [Data Relationships]
  - Strictly forbidden to use business interpretation vocabulary (e.g., "healthy," "weak," "risk," "advantage," etc.)
  - Use neutral morphological vocabulary to describe "what patterns are seen," not "what this means"

**[Core Insights]**
- **Task:** Based on the pattern characteristics above, distill business-level conclusions and implications. This is the "business interpretation layer," not the "morphological description layer."
- **Content Structure (strictly follow):**
  ```
  Core Conclusion: (The most important business judgment, ≤30 words)

  Business Implications:
  - Implication 1 (What business situation/problem/advantage does this pattern indicate? ≤20 words)
  - Implication 2 (What impact on which aspect/metric/capability? ≤20 words)
  - Implication 3 (If applicable, further business inference, ≤20 words)

  Risk Concerns:
  - Risk Point 1 (Specific threshold + possible consequences, ≤25 words)
  - Risk Point 2 (If applicable, specific threshold + possible consequences, ≤25 words)
  ```
- **Requirements:**
  - Total word count around 250 words, using straightforward business language
  - **Strictly forbidden to repeat morphological descriptions from [Pattern Characteristics]** (e.g., morphological terms like "rising," "divergence," "volatility")
  - **"Business Implications" must be business-level interpretations**, answering one of the following questions:
    - What situation does this pattern indicate? (e.g., profitability, market sentiment, risk level, allocation efficiency, correlation strength)
    - What impact on what? (e.g., impact on decisions, impact on risk exposure, implications for asset allocation, impact on liquidity)
    - What characteristics does it reflect? (e.g., stability, dependency, concentration, sensitivity, symmetry, periodicity)
  - **"Risk Concerns" must include specific information:**
    - Clear numerical thresholds or critical points
    - Straightforward possible consequences or impacts
    - Avoid abstract or vague expressions
  - Strictly forbidden to cite any information not appearing in the chart"""

# Human prompt 简化，详细指令已在 system 中
USER_PROMPT_ZH = "请分析这张金融图表。"
USER_PROMPT_EN = "Please analyze this financial chart."


def detect_language(dir_name: str) -> str:
    """从目录名检测语言"""
    if "zh-CN" in dir_name:
        return "zh"
    elif "en-US" in dir_name:
        return "en"
    return "en"


def build_sample(image_path: str, analysis: str, lang: str) -> Dict:
    """构建 ShareGPT 格式样本"""
    if lang == "zh":
        system_prompt = SYSTEM_PROMPT_ZH
        user_prompt = USER_PROMPT_ZH
    else:
        system_prompt = SYSTEM_PROMPT_EN
        user_prompt = USER_PROMPT_EN

    return {
        "messages": [
            {"from": "system", "value": system_prompt},
            {"from": "human", "value": f"<image>\n{user_prompt}"},
            {"from": "gpt", "value": analysis}
        ],
        "images": [image_path]
    }


def get_valid_v3_samples(source_dir: Path, prefix: str) -> List[Tuple[Path, str, str]]:
    """获取 V3 格式的有效样本 (有 chart.png 和 analysis.txt)
    返回: [(subdir, output_image_name, lang), ...]
    """
    valid = []
    if not source_dir.exists():
        print(f"⚠️ 目录不存在: {source_dir}")
        return valid

    for subdir in source_dir.iterdir():
        if not subdir.is_dir() or subdir.name.startswith((".", "_")):
            continue

        chart_file = subdir / "chart.png"
        analysis_file = subdir / "analysis.txt"

        if chart_file.exists() and analysis_file.exists():
            try:
                content = analysis_file.read_text(encoding="utf-8").strip()
                if content:
                    lang = detect_language(subdir.name)
                    output_name = f"{prefix}{subdir.name}.png"
                    valid.append((subdir, output_name, lang))
            except Exception:
                pass

    return valid


def get_valid_v4_samples(source_dir: Path) -> List[Tuple[Path, str, str]]:
    """获取 V4 格式的有效样本 (有 artifacts/chart.png 和 summary/analysis*.txt)
    返回: [(subdir, dir_name, lang), ...]
    """
    valid = []
    if not source_dir.exists():
        print(f"⚠️ 目录不存在: {source_dir}")
        return valid

    for subdir in source_dir.iterdir():
        if not subdir.is_dir() or subdir.name.startswith((".", "_")):
            continue

        chart_file = subdir / "artifacts" / "chart.png"
        if not chart_file.exists():
            continue

        lang = detect_language(subdir.name)

        # 中文用 analysis.txt，英文用 analysis_en.txt
        if lang == "zh":
            analysis_file = subdir / "summary" / "analysis.txt"
        else:
            analysis_file = subdir / "summary" / "analysis_en.txt"

        if analysis_file.exists():
            try:
                content = analysis_file.read_text(encoding="utf-8").strip()
                if content:
                    valid.append((subdir, subdir.name, lang))
            except Exception:
                pass

    return valid


def get_exclude_set() -> Set[str]:
    """获取需要排除的目录名集合 (从 sync_300_cn 和 sync_300_en)"""
    exclude = set()
    for exclude_dir in EXCLUDE_DIRS:
        if exclude_dir.exists():
            for subdir in exclude_dir.iterdir():
                if subdir.is_dir():
                    exclude.add(subdir.name)
    return exclude


def process_and_copy_v3(samples: List[Tuple[Path, str, str]], limit: int = None) -> List[Dict]:
    """处理 V3 样本，复制图片并生成数据"""
    if limit and len(samples) > limit:
        random.shuffle(samples)
        samples = samples[:limit]

    results = []
    for subdir, output_name, lang in tqdm(samples, desc="  复制"):
        chart_file = subdir / "chart.png"
        analysis_file = subdir / "analysis.txt"
        output_path = IMAGES_DIR / output_name

        # 复制图片
        shutil.copy2(chart_file, output_path)

        # 读取分析
        analysis = analysis_file.read_text(encoding="utf-8").strip()

        # 构建样本
        sample = build_sample(f"images/{output_name}", analysis, lang)
        results.append(sample)

    return results


def process_and_copy_v4(samples: List[Tuple[Path, str, str]], prefix: str, limit: int = None) -> List[Dict]:
    """处理 V4 样本，复制图片并生成数据"""
    if limit and len(samples) > limit:
        random.shuffle(samples)
        samples = samples[:limit]

    results = []
    for subdir, dir_name, lang in tqdm(samples, desc="  复制"):
        chart_file = subdir / "artifacts" / "chart.png"

        if lang == "zh":
            analysis_file = subdir / "summary" / "analysis.txt"
        else:
            analysis_file = subdir / "summary" / "analysis_en.txt"

        output_name = f"{prefix}{dir_name}.png"
        output_path = IMAGES_DIR / output_name

        # 复制图片
        shutil.copy2(chart_file, output_path)

        # 读取分析
        analysis = analysis_file.read_text(encoding="utf-8").strip()

        # 构建样本
        sample = build_sample(f"images/{output_name}", analysis, lang)
        results.append(sample)

    return results


def process_fin_chart() -> List[Dict]:
    """处理 fin-chart 数据 (mc_ 前缀)"""
    samples = []
    fin_chart_dir = DATA_DIR / "fin-chart"

    if not fin_chart_dir.exists():
        print(f"⚠️ fin-chart 目录不存在")
        return samples

    subdirs = [d for d in fin_chart_dir.iterdir() if d.is_dir()]

    for subdir in tqdm(subdirs, desc="  处理 fin-chart"):
        # 查找图片 (jpg 格式)
        jpg_files = list(subdir.glob("*.jpg"))
        if not jpg_files:
            continue
        image_file = jpg_files[0]

        # 优先使用英文分析
        analysis_file = subdir / "analysis_en.txt"
        if not analysis_file.exists():
            analysis_file = subdir / "analysis.txt"

        if not analysis_file.exists():
            continue

        try:
            analysis = analysis_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue

        if not analysis:
            continue

        # 输出图片名 (保持原名，已有 mc_ 前缀)
        output_image_name = image_file.name
        output_image_path = IMAGES_DIR / output_image_name

        # 复制图片 (如果不存在)
        if not output_image_path.exists():
            shutil.copy2(image_file, output_image_path)

        # fin-chart 使用英文
        sample = build_sample(f"images/{output_image_name}", analysis, "en")
        samples.append(sample)

    return samples


def process_finmme() -> List[Dict]:
    """处理 finmme 数据 (finmme_ 前缀)"""
    samples = []
    finmme_dir = DATA_DIR / "finmme"

    if not finmme_dir.exists():
        print(f"⚠️ finmme 目录不存在")
        return samples

    subdirs = [d for d in finmme_dir.iterdir() if d.is_dir()]

    for subdir in tqdm(subdirs, desc="  处理 finmme"):
        # 查找图片 (png 格式)
        png_files = list(subdir.glob("*.png"))
        if not png_files:
            continue
        image_file = png_files[0]

        # 优先使用英文分析
        analysis_file = subdir / "analysis_en.txt"
        if not analysis_file.exists():
            analysis_file = subdir / "analysis.txt"

        if not analysis_file.exists():
            continue

        try:
            analysis = analysis_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue

        if not analysis:
            continue

        # 输出图片名 (保持原名，已有 finmme_ 前缀)
        output_image_name = image_file.name
        output_image_path = IMAGES_DIR / output_image_name

        # 复制图片 (如果不存在)
        if not output_image_path.exists():
            shutil.copy2(image_file, output_image_path)

        # finmme 使用英文
        sample = build_sample(f"images/{output_image_name}", analysis, "en")
        samples.append(sample)

    return samples


def split_dataset(samples: List[Dict], train_ratio: float = 0.8) -> Tuple[List[Dict], List[Dict]]:
    """划分训练/验证集"""
    shuffled = samples.copy()
    random.shuffle(shuffled)
    split_idx = int(len(shuffled) * train_ratio)
    return shuffled[:split_idx], shuffled[split_idx:]


def save_json(data: List[Dict], filepath: Path):
    """保存 JSON"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    random.seed(RANDOM_SEED)

    print("=" * 60)
    print("🚀 重建训练数据集 (全部从源目录生成)")
    print("=" * 60)

    all_samples = []

    # ============== 1. prog_ (1000张) ==============
    print("\n📦 1. 处理 prog_ (目标: 1000 张)...")

    # 先删除现有的 prog_ 图片
    for f in IMAGES_DIR.glob("prog_*.png"):
        f.unlink()

    prog_valid = get_valid_v3_samples(PROG_SOURCE, "prog_")
    print(f"   有效样本: {len(prog_valid)}")

    prog_samples = process_and_copy_v3(prog_valid, limit=TARGET_COUNT)
    all_samples.extend(prog_samples)
    print(f"   ✅ 保留: {len(prog_samples)} 张")

    # ============== 2. syn_ (全部保留) ==============
    print("\n📦 2. 处理 syn_ (全部保留)...")

    # 先删除现有的 syn_ 图片 (但不删除 syn_v2_, syn_v4_, syn_v4f_)
    for f in IMAGES_DIR.glob("syn_*.png"):
        name = f.name
        if not (name.startswith("syn_v2_") or name.startswith("syn_v4_") or name.startswith("syn_v4f_")):
            f.unlink()

    syn_valid = get_valid_v3_samples(SYN_SOURCE, "syn_")
    print(f"   有效样本: {len(syn_valid)}")

    syn_samples = process_and_copy_v3(syn_valid, limit=None)  # 不限制数量
    all_samples.extend(syn_samples)
    print(f"   ✅ 保留: {len(syn_samples)} 张")

    # ============== 3. syn_v2_ (1000张) ==============
    print("\n📦 3. 处理 syn_v2_ (目标: 1000 张)...")

    for f in IMAGES_DIR.glob("syn_v2_*.png"):
        f.unlink()

    syn_v2_valid = get_valid_v3_samples(SYN_V2_SOURCE, "syn_v2_")
    print(f"   有效样本: {len(syn_v2_valid)}")

    syn_v2_samples = process_and_copy_v3(syn_v2_valid, limit=TARGET_COUNT)
    all_samples.extend(syn_v2_samples)
    print(f"   ✅ 保留: {len(syn_v2_samples)} 张")

    # ============== 4. syn_v4_ (1000张) ==============
    print("\n📦 4. 从 batch_2000 采样 syn_v4_ (目标: 1000 张)...")

    for f in IMAGES_DIR.glob("syn_v4_*.png"):
        f.unlink()

    batch_2000_valid = get_valid_v4_samples(BATCH_2000)
    print(f"   有效样本: {len(batch_2000_valid)}")

    syn_v4_samples = process_and_copy_v4(batch_2000_valid, "syn_v4_", limit=TARGET_COUNT)
    all_samples.extend(syn_v4_samples)
    print(f"   ✅ 采样: {len(syn_v4_samples)} 张")

    # ============== 5. syn_v4f_ (过滤后全部) ==============
    print("\n📦 5. 从 batch_1000_final 采样 syn_v4f_ (排除 sync_300_cn/en)...")

    for f in IMAGES_DIR.glob("syn_v4f_*.png"):
        f.unlink()

    exclude_set = get_exclude_set()
    print(f"   排除集合大小: {len(exclude_set)}")

    batch_1000_valid = get_valid_v4_samples(BATCH_1000_FINAL)
    batch_1000_filtered = [(s, n, l) for s, n, l in batch_1000_valid if n not in exclude_set]
    print(f"   有效样本: {len(batch_1000_valid)}, 过滤后: {len(batch_1000_filtered)}")

    syn_v4f_samples = process_and_copy_v4(batch_1000_filtered, "syn_v4f_")
    all_samples.extend(syn_v4f_samples)
    print(f"   ✅ 采样: {len(syn_v4f_samples)} 张")

    # ============== 6. mc_ (fin-chart) ==============
    print("\n📦 6. 处理 mc_ (fin-chart)...")
    mc_samples = process_fin_chart()
    all_samples.extend(mc_samples)
    print(f"   ✅ 处理: {len(mc_samples)} 张")

    # ============== 7. finmme_ ==============
    print("\n📦 7. 处理 finmme_...")
    finmme_samples = process_finmme()
    all_samples.extend(finmme_samples)
    print(f"   ✅ 处理: {len(finmme_samples)} 张")

    # ============== 8. 划分并保存 ==============
    print("\n📝 划分数据集 (80/20)...")

    train_data, val_data = split_dataset(all_samples, TRAIN_RATIO)

    save_json(train_data, DATA_DIR / "all_train.json")
    save_json(val_data, DATA_DIR / "all_val.json")

    print(f"   ✅ all_train.json: {len(train_data)} 条")
    print(f"   ✅ all_val.json: {len(val_data)} 条")

    # ============== 统计 ==============
    print("\n" + "=" * 60)
    print("📊 最终统计:")
    print("=" * 60)

    # 按前缀统计
    prefix_counts = {}
    for s in all_samples:
        img_name = os.path.basename(s["images"][0])
        for prefix in ["syn_v4f_", "syn_v4_", "syn_v2_", "syn_", "prog_", "mc_", "finmme_"]:
            if img_name.startswith(prefix):
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
                break

    print("\n| 前缀 | 数量 |")
    print("|------|------|")
    for prefix in ["prog_", "syn_", "syn_v2_", "syn_v4_", "syn_v4f_", "mc_", "finmme_"]:
        count = prefix_counts.get(prefix, 0)
        print(f"| {prefix} | {count} |")
    print(f"| **总计** | **{len(all_samples)}** |")

    print(f"\n训练集: {len(train_data)} | 验证集: {len(val_data)}")
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()
