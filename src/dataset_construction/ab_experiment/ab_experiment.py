"""
A/B 对比实验脚本 (异步并发版本)
==============================
对比两种提示词策略的效果：
- A组：仅使用系统提示词（纯视觉分析）
- B组：系统提示词 + 内部参考信息（带数据辅助）

使用 Gemini 2.5 Flash 进行生成，异步并发调用
"""

import json
import base64
import random
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import aiofiles

from openai import AsyncOpenAI

# 添加 scripts 目录到路径
SCRIPTS_DIR = Path("<WORKSPACE>/合成图表/chart-synthesis-v3/scripts")
sys.path.insert(0, str(SCRIPTS_DIR))

from data_processors import classify_data_type, process_time_series, process_cross_section, DataType

# ============== 配置 ==============

API_KEY = '<YOUR_API_KEY>'
BASE_URL = '<YOUR_LLM_PROXY>/v1'
MODEL = 'gemini-2.5-flash-preview-09-2025'

# 并发配置
MAX_CONCURRENCY = 20  # 最大并发数

# 数据处理阈值
MAX_RAW_POINTS = 200
MAX_HEAD_TAIL = 50

# 路径配置
BATCH_DIR = Path("<WORKSPACE>/合成图表/chart-synthesis-v3/prog_2000/batch_004")
OUTPUT_DIR = Path("<WORKSPACE>/合成图表/test/ab_experiment_results")

# ============== 提示词模板 ==============

SYSTEM_PROMPT_ZH = """你是一位严谨的、专注于金融领域的图表分析专家。你的唯一任务是接收一张金融图表，并严格遵循一个由四部分组成的结构，生成一份客观、独立的分析报告。

核心规则:
1. 遵循结构: 你的报告必须严格包含【图表构成】、【数据关系】、【模式特征】、和【核心洞察】这四个部分的标题。
2. 信息封闭原则: 你的所有分析，尤其是【核心洞察】部分，必须完全且仅来源于图表本身的视觉信息。严禁引入任何图表之外的市场新闻、宏观事件、公司背景或进行预测。
3. 纯净输出: 你的回答必须是纯文本，直接从【图表构成】开始，报告结束后不添加任何附言或总结。

格式要求:
- 禁止使用 markdown 格式（如 **加粗**、# 标题、`代码块`）
- 章节标题只用【】包裹，不加任何修饰
- 列表项直接用 "- " 开头，禁止使用 "- xxx：" 格式的小标题前缀
- 输出纯文本格式，保持简洁

---

请严格按照以下四层结构，并坚守信息封闭原则，分析你看到的金融图表：

【图表构成】
- 任务: 简洁描述图表的基础构成元素
- 内容: 图表类型、标题、坐标轴/维度的范围和标签（如有）、图例（颜色/样式编码）。只描述关键元素，无需穷尽所有细节。

【数据关系】
- 任务: 提取图表中最关键的、可量化的数据事实
- 内容:
  - 关键数值及其位置（如：极值、关键点位、重要时点的数据）
  - 主要的数量关系（如：变动幅度、占比、差距、相关系数、分布范围）
  - 数据点之间的简单对比（如：A与B的关系、前后的变化）
- 要求:
  - 只列出对理解图表重要的数据关系
  - 确保数值准确，忠实于图表

【模式特征】
- 任务: 用几句话纯粹描述数据的形态特征，不做任何业务解读
- 内容:
  - 整体形态（如时序图：趋势方向、波动幅度、周期性；如分布图：集中度、对称性、聚类特征；如关系图：相关性分布、线性程度）
  - 结构特点（如：均衡/失衡、连续/跳跃、单一主导/多元分散）
  - 明显的异常、拐点或例外（如有）
- 要求:
  - 这是纯粹的"形态层"，只描述数据的视觉模式
  - 避免重复【数据关系】中的具体数值
  - 严禁使用业务解读词汇（如"健康""疲软""风险""优势"等）
  - 用中性的形态词汇描述"看到的模式是什么"，而非"这意味着什么"

【核心洞察】
- 任务: 基于前面的形态特征，提炼业务层面的结论和影响。这是"业务解读层"，而非"形态描述层"。
- 内容结构（严格遵循）:
  核心结论：（最重要的业务判断，≤30字）

  业务含义：
  - 说明业务状况/问题/优势（≤20字）
  - 说明对环节/指标/能力的影响（≤20字）
  - 进一步的业务推论（如有，≤20字）

  风险关注：
  - 具体阈值+可能后果（≤25字）
  - 另一风险点（如有，≤25字）
- 要求:
  - 总字数控制在250字左右，使用直白的商业语言
  - 严禁重复【模式特征】中的形态描述（如"上升""背离""波动"等形态词汇）
  - "业务含义"必须是业务层面的解读
  - "风险关注"必须包含具体信息：明确的数字阈值或临界点，直白的可能后果或影响
  - 严禁引用任何未在图表中出现的信息"""

SYSTEM_PROMPT_EN = """You are a rigorous financial chart analysis expert. Your sole task is to receive a financial chart and generate an objective, independent analysis report following a strict four-part structure.

Core Rules:
1. Follow Structure: Your report must strictly contain these four section titles: [Chart Composition], [Data Relationships], [Pattern Features], and [Key Insights].
2. Information Closure Principle: All your analysis, especially [Key Insights], must be derived solely from the visual information in the chart. Do not introduce any external market news, macro events, company background, or make predictions.
3. Clean Output: Your response must be plain text, starting directly from [Chart Composition], with no postscript or summary after the report.

Format Requirements:
- Do not use markdown formatting (such as **bold**, # headings, `code blocks`)
- Section titles should only be wrapped in [], with no additional decoration
- List items should start directly with "- ", avoid using "- xxx:" prefix format
- Output in plain text format, keep it concise

---

Strictly follow the four-layer structure below, adhering to the information closure principle, to analyze the financial chart you see:

[Chart Composition]
- Task: Briefly describe the basic elements of the chart
- Content: Chart type, title, axis/dimension ranges and labels (if any), legend (color/style encoding). Only describe key elements, no need to exhaustively list all details.

[Data Relationships]
- Task: Extract the most critical, quantifiable data facts from the chart
- Content:
  - Key values and their positions (e.g., extremes, key levels, important time points)
  - Main quantitative relationships (e.g., change magnitude, proportions, gaps, correlation coefficients, distribution ranges)
  - Simple comparisons between data points (e.g., A vs B relationship, before/after changes)
- Requirements:
  - Only list data relationships important for understanding the chart
  - Ensure values are accurate and faithful to the chart

[Pattern Features]
- Task: Describe the morphological characteristics of the data in a few sentences, without any business interpretation
- Content:
  - Overall shape (e.g., for time series: trend direction, volatility amplitude, periodicity; for distribution charts: concentration, symmetry, clustering features; for relationship charts: correlation distribution, linearity)
  - Structural characteristics (e.g., balanced/imbalanced, continuous/discontinuous, single-dominant/multi-dispersed)
  - Notable anomalies, inflection points, or exceptions (if any)
- Requirements:
  - This is purely the "morphology layer", only describing visual patterns in the data
  - Avoid repeating specific values from [Data Relationships]
  - Strictly avoid business interpretation terms (such as "healthy", "weak", "risk", "advantage")
  - Use neutral morphological vocabulary to describe "what patterns are seen", not "what this means"

[Key Insights]
- Task: Based on the pattern features above, distill business-level conclusions and implications. This is the "business interpretation layer", not the "pattern description layer".
- Content Structure (follow strictly):
  Core Conclusion: (The most important business judgment, ≤15 words)

  Business Implications:
  - Describe business condition/issue/advantage (≤12 words)
  - Describe impact on processes/metrics/capabilities (≤12 words)
  - Further business inference (if any, ≤12 words)

  Risk Considerations:
  - Specific threshold + possible consequence (≤15 words)
  - Another risk point (if any, ≤15 words)
- Requirements:
  - Keep total word count around 150 words, use straightforward business language
  - Strictly avoid repeating morphological descriptions from [Pattern Features] (such as "rising", "diverging", "fluctuating")
  - "Business Implications" must be business-level interpretations
  - "Risk Considerations" must include specific information: clear numerical thresholds or critical points, straightforward possible consequences
  - Strictly do not reference any information not appearing in the chart"""

INTERNAL_REFERENCE_TEMPLATE_ZH = """
---
【内部参考信息】
以下信息仅供验证你的视觉分析准确性，请勿在输出中提及这些参考信息的存在。
你的分析应当看起来完全基于图表视觉信息。

[元数据]
图表类型: {chart_type}
数据来源: {data_source}
时间范围: {time_range}
数据点数: {data_points}

[数据摘要]
{data_summary}
---"""

INTERNAL_REFERENCE_TEMPLATE_EN = """
---
[Internal Reference Information]
The following information is only for verifying the accuracy of your visual analysis. Do not mention the existence of this reference information in your output.
Your analysis should appear to be entirely based on the visual information in the chart.

[Metadata]
Chart Type: {chart_type}
Data Source: {data_source}
Time Range: {time_range}
Data Points: {data_points}

[Data Summary]
{data_summary}
---"""


# ============== 工具函数 ==============

def load_json(path: Path) -> Dict[str, Any]:
    """加载 JSON 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def encode_image(image_path: Path) -> str:
    """将图片编码为 base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def get_chart_dirs_with_images(batch_dir: Path) -> List[Path]:
    """获取所有有图片的图表目录"""
    chart_dirs = []
    for d in batch_dir.iterdir():
        if d.is_dir() and (d / "artifacts" / "chart.png").exists():
            chart_dirs.append(d)
    return chart_dirs


def get_prompts_by_language(language: str):
    """根据语言获取提示词"""
    if language == "zh-CN":
        return SYSTEM_PROMPT_ZH, INTERNAL_REFERENCE_TEMPLATE_ZH
    else:
        return SYSTEM_PROMPT_EN, INTERNAL_REFERENCE_TEMPLATE_EN


def build_data_summary(chart_dir: Path) -> str:
    """构建数据摘要"""
    dataspec_path = chart_dir / "dataspec.json"
    metadata_path = chart_dir / "metadata.json"
    raw_csv_path = chart_dir / "data" / "raw.csv"

    if not all(p.exists() for p in [dataspec_path, metadata_path, raw_csv_path]):
        return "数据文件缺失"

    dataspec = load_json(dataspec_path)
    metadata = load_json(metadata_path)

    data_type = classify_data_type(dataspec, metadata)
    data_points = metadata.get('data_source', {}).get('data_points', 0)

    if data_type in [DataType.TIME_SERIES_LONG, DataType.TIME_SERIES_SHORT]:
        return process_time_series(raw_csv_path, data_points, max_raw=MAX_RAW_POINTS)
    else:
        return process_cross_section(raw_csv_path, data_points, max_raw=MAX_RAW_POINTS, head_tail=MAX_HEAD_TAIL)


def prepare_chart_data(chart_dir: Path) -> Dict:
    """预处理图表数据（同步，在主线程执行）"""
    chart_id = chart_dir.name

    # 加载元数据
    metadata = load_json(chart_dir / "metadata.json")
    language = metadata.get("language", "en-US")
    chart_type = metadata.get("chart_type", "unknown")
    time_range = metadata.get("data_source", {}).get("time_range", "unknown")
    data_points = metadata.get("data_source", {}).get("data_points", 0)

    # 获取对应语言的提示词
    system_prompt, internal_ref_template = get_prompts_by_language(language)

    # 编码图片
    image_path = chart_dir / "artifacts" / "chart.png"
    base64_image = encode_image(image_path)

    # 构建数据摘要
    data_summary = build_data_summary(chart_dir)

    # 从 dataspec 获取数据来源
    dataspec_path = chart_dir / "dataspec.json"
    if dataspec_path.exists():
        dataspec = load_json(dataspec_path)
        data_source = dataspec.get('what', {}).get('data_source', 'Synthetic')
    else:
        data_source = 'Synthetic'

    # 构建内部参考信息
    internal_ref = internal_ref_template.format(
        chart_type=chart_type,
        data_source=data_source,
        time_range=time_range,
        data_points=data_points,
        data_summary=data_summary
    )

    return {
        "chart_id": chart_id,
        "chart_dir": chart_dir,
        "language": language,
        "chart_type": chart_type,
        "system_prompt": system_prompt,
        "base64_image": base64_image,
        "internal_ref": internal_ref
    }


async def call_api_async(
    client: AsyncOpenAI,
    system_prompt: str,
    user_content: list,
    model: str = MODEL
) -> tuple[str, dict]:
    """异步调用 API"""
    start_time = datetime.now()

    completion = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        max_completion_tokens=4096
    )

    duration = (datetime.now() - start_time).total_seconds()
    analysis = completion.choices[0].message.content or ""

    usage = {
        "prompt_tokens": completion.usage.prompt_tokens if completion.usage else None,
        "completion_tokens": completion.usage.completion_tokens if completion.usage else None,
        "total_tokens": completion.usage.total_tokens if completion.usage else None,
        "duration_s": round(duration, 2)
    }

    return analysis, usage


async def process_single_chart_async(
    client: AsyncOpenAI,
    chart_data: Dict,
    group: str,  # "A" or "B"
    semaphore: asyncio.Semaphore
) -> Dict:
    """异步处理单个图表"""
    async with semaphore:
        chart_id = chart_data["chart_id"]

        # 构建用户内容
        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{chart_data['base64_image']}",
                    "detail": "high"
                }
            }
        ]

        # B组添加内部参考信息
        if group == "B":
            user_content.append({
                "type": "text",
                "text": chart_data["internal_ref"]
            })

        try:
            analysis, usage = await call_api_async(
                client,
                chart_data["system_prompt"],
                user_content
            )

            return {
                "chart_id": chart_id,
                "group": group,
                "language": chart_data["language"],
                "chart_type": chart_data["chart_type"],
                "analysis": analysis,
                "usage": usage,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
        except Exception as e:
            return {
                "chart_id": chart_id,
                "group": group,
                "language": chart_data["language"],
                "chart_type": chart_data["chart_type"],
                "analysis": "",
                "usage": {},
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": str(e)
            }


async def run_experiment_async(
    sample_size: int = 100,
    random_seed: int = 42
):
    """异步运行对比实验"""
    print(f"🔬 开始 A/B 对比实验 (异步并发版本)")
    print(f"   模型: {MODEL}")
    print(f"   样本量: {sample_size}")
    print(f"   最大并发: {MAX_CONCURRENCY}")
    print(f"   随机种子: {random_seed}")
    print()

    # 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 获取所有有图的目录
    all_chart_dirs = get_chart_dirs_with_images(BATCH_DIR)
    print(f"📁 找到 {len(all_chart_dirs)} 个有图的图表目录")

    # 随机抽样
    random.seed(random_seed)
    sample_dirs = random.sample(all_chart_dirs, min(sample_size, len(all_chart_dirs)))
    print(f"🎲 随机抽取 {len(sample_dirs)} 个样本")
    print()

    # 保存样本列表
    sample_list = [d.name for d in sample_dirs]
    with open(OUTPUT_DIR / "sample_list.json", 'w', encoding='utf-8') as f:
        json.dump({
            "sample_size": len(sample_dirs),
            "random_seed": random_seed,
            "samples": sample_list
        }, f, ensure_ascii=False, indent=2)

    # 预处理所有图表数据（同步）
    print("📊 预处理图表数据...")
    all_chart_data = []
    for i, chart_dir in enumerate(sample_dirs, 1):
        try:
            chart_data = prepare_chart_data(chart_dir)
            all_chart_data.append(chart_data)
        except Exception as e:
            print(f"   ⚠️ 跳过 {chart_dir.name}: {e}")
    print(f"   ✅ 成功预处理 {len(all_chart_data)} 个图表")
    print()

    # 初始化异步 API 客户端
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    # 创建所有任务（A组和B组）
    print("🚀 开始并发调用 API...")
    start_time = datetime.now()

    tasks_a = [
        process_single_chart_async(client, data, "A", semaphore)
        for data in all_chart_data
    ]
    tasks_b = [
        process_single_chart_async(client, data, "B", semaphore)
        for data in all_chart_data
    ]

    # 合并所有任务并执行
    all_tasks = tasks_a + tasks_b
    all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

    total_duration = (datetime.now() - start_time).total_seconds()

    # 分离结果
    results_a = []
    results_b = []

    for i, result in enumerate(all_results):
        if isinstance(result, Exception):
            print(f"   ❌ 任务 {i} 异常: {result}")
            continue

        if result["group"] == "A":
            results_a.append(result)
        else:
            results_b.append(result)

    # 统计成功/失败
    success_a = sum(1 for r in results_a if r.get("status") == "success")
    success_b = sum(1 for r in results_b if r.get("status") == "success")

    print()
    print(f"⏱️  总耗时: {total_duration:.1f}s")
    print(f"   A组: {success_a}/{len(results_a)} 成功")
    print(f"   B组: {success_b}/{len(results_b)} 成功")

    # 保存最终结果
    save_final_results(results_a, results_b)

    print()
    print(f"✅ 实验完成!")
    print(f"   结果保存在: {OUTPUT_DIR}")


def save_final_results(results_a: list, results_b: list):
    """保存最终结果"""
    # 保存 A 组结果
    with open(OUTPUT_DIR / "results_group_a.json", 'w', encoding='utf-8') as f:
        json.dump(results_a, f, ensure_ascii=False, indent=2)

    # 保存 B 组结果
    with open(OUTPUT_DIR / "results_group_b.json", 'w', encoding='utf-8') as f:
        json.dump(results_b, f, ensure_ascii=False, indent=2)

    # 构建 chart_id 到结果的映射
    results_a_map = {r["chart_id"]: r for r in results_a}
    results_b_map = {r["chart_id"]: r for r in results_b}

    # 保存合并的对比结果
    combined = []
    for chart_id in results_a_map:
        if chart_id in results_b_map:
            ra = results_a_map[chart_id]
            rb = results_b_map[chart_id]
            combined.append({
                "chart_id": chart_id,
                "language": ra["language"],
                "chart_type": ra["chart_type"],
                "group_a": {
                    "analysis": ra["analysis"],
                    "usage": ra["usage"],
                    "status": ra.get("status", "unknown")
                },
                "group_b": {
                    "analysis": rb["analysis"],
                    "usage": rb["usage"],
                    "status": rb.get("status", "unknown")
                }
            })

    with open(OUTPUT_DIR / "results_combined.json", 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    # 生成统计摘要
    summary = generate_summary(results_a, results_b)
    with open(OUTPUT_DIR / "experiment_summary.json", 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def generate_summary(results_a: list, results_b: list) -> dict:
    """生成实验统计摘要"""
    def calc_stats(results):
        successful = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") != "success"]

        if not successful:
            return {"count": 0, "success": 0, "failed": len(failed)}

        total_tokens = sum(r['usage'].get('total_tokens', 0) or 0 for r in successful)
        total_duration = sum(r['usage'].get('duration_s', 0) for r in successful)
        avg_analysis_len = sum(len(r['analysis']) for r in successful) / len(successful)

        return {
            "count": len(results),
            "success": len(successful),
            "failed": len(failed),
            "total_tokens": total_tokens,
            "avg_tokens": round(total_tokens / len(successful), 0),
            "total_duration_s": round(total_duration, 2),
            "avg_duration_s": round(total_duration / len(successful), 2),
            "avg_analysis_length": round(avg_analysis_len, 0)
        }

    return {
        "experiment_info": {
            "model": MODEL,
            "max_concurrency": MAX_CONCURRENCY,
            "timestamp": datetime.now().isoformat(),
            "batch_source": str(BATCH_DIR)
        },
        "group_a": {
            "description": "仅系统提示词（纯视觉分析）",
            "stats": calc_stats(results_a)
        },
        "group_b": {
            "description": "系统提示词 + 内部参考信息（带数据辅助）",
            "stats": calc_stats(results_b)
        }
    }


def main():
    asyncio.run(run_experiment_async(sample_size=100, random_seed=42))


if __name__ == "__main__":
    main()
