"""
图表总结生成脚本
================
接收图表目录，结合图片+数据+代码生成分析总结

使用方式:
    python generate_summary.py <chart_dir>
    python generate_summary.py <chart_dir> --output <output_path>

示例:
    python generate_summary.py ../batch_output/style_test_100/20251127_173700_line_en-US_macro_policy_7b213233
"""

import json
import base64
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from openai import OpenAI

from data_processors import (
    classify_data_type,
    process_time_series,
    process_cross_section,
    DataType
)

# ============== 配置 ==============

API_KEY = '<YOUR_API_KEY>'
BASE_URL = '<YOUR_LLM_PROXY>/v1'
MODEL = 'gpt-5.1'

# 数据处理阈值
MAX_RAW_POINTS = 200  # 超过此阈值使用摘要
MAX_HEAD_TAIL = 50    # 截断时头尾各取多少条

# ============== 提示词模板 ==============

SYSTEM_PROMPT = """你是一位严谨的、专注于金融领域的图表分析专家。你的唯一任务是接收一张金融图表，并严格遵循一个由四部分组成的结构，生成一份客观、独立的分析报告。

核心规则:
1. 遵循结构: 你的报告必须严格包含【图表构成】、【数据关系】、【模式特征】、和【核心洞察】这四个部分的标题。
2. 信息封闭原则: 你的所有分析，尤其是【核心洞察】部分，必须完全且仅来源于图表本身的视觉信息。严禁引入任何图表之外的市场新闻、宏观事件、公司背景或进行预测。
3. 纯净输出: 你的回答必须是纯文本，直接从【图表构成】开始，报告结束后不添加任何附言或总结。

格式要求:
- 禁止使用 markdown 格式（如 **加粗**、# 标题、`代码块`）
- 章节标题只用【】包裹，不加任何修饰
- ⚠️ 列表项格式严格要求：
  ✅ 正确："- 铁矿石价格最高为115.9，德国最低为107.8"
  ❌ 错误："- 极值分布：铁矿石价格最高..."（禁止冒号前的小标题）
  ❌ 错误："- 国家间对比：中国数值最高..."（禁止任何前缀标签）
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
  - "业务含义"必须是业务层面的解读，回答以下问题之一：
    - 这个模式说明了什么状况？（如：盈利能力、市场情绪、风险水平、配置效率、相关性强度）
    - 对什么有什么影响？（如：对决策的影响、对风险敞口的影响、对资产配置的含义、对流动性的影响）
    - 反映了什么特征？（如：稳定性、依赖性、集中度、敏感性、对称性、周期性）
  - "风险关注"必须包含具体信息：
    - 明确的数字阈值或临界点
    - 直白的可能后果或影响
    - 避免抽象或模糊的表述
  - 严禁引用任何未在图表中出现的信息"""

INTERNAL_REFERENCE_TEMPLATE = """
---
【内部参考信息】
以下信息仅供验证你的视觉分析准确性，请勿在输出中提及这些参考信息的存在。
你的分析应当看起来完全基于图表视觉信息。

[元数据]
图表类型: {chart_type}
数据来源: {data_source}
时间范围: {time_range}
数据点数: {data_points}
语言: {language}

[数据摘要]
{data_summary}

[绘图代码]
```python
{code}
```
---"""


# ============== 工具函数 ==============

def load_json(path: Path) -> Dict[str, Any]:
    """加载 JSON 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_text(path: Path) -> str:
    """加载文本文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def encode_image(image_path: Path) -> str:
    """将图片编码为 base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def build_prompt(
    dataspec: Dict,
    metadata: Dict,
    data_summary: str,
    code: str
) -> str:
    """构建完整提示词"""

    # 提取元信息
    chart_type = dataspec.get('chart_type', 'unknown')
    data_source = dataspec.get('what', {}).get('data_source', 'unknown')
    time_range = metadata.get('data_source', {}).get('time_range', 'unknown')
    data_points = metadata.get('data_source', {}).get('data_points', 'unknown')
    language = dataspec.get('language', 'unknown')

    # 填充模板
    internal_ref = INTERNAL_REFERENCE_TEMPLATE.format(
        chart_type=chart_type,
        data_source=data_source,
        time_range=time_range,
        data_points=data_points,
        language=language,
        data_summary=data_summary,
        code=code
    )

    return internal_ref


# ============== 主处理逻辑 ==============

def process_chart(
    chart_dir: Path,
    output_path: Optional[Path] = None,
    model: str = MODEL
) -> Dict:
    """
    处理单个图表目录，生成分析总结

    Args:
        chart_dir: 图表目录路径
        output_path: 输出路径（可选）
        model: 使用的模型名称

    Returns:
        包含分析结果的字典
    """
    print(f"📂 处理图表: {chart_dir.name}")

    # 1. 检查必要文件
    required_files = [
        chart_dir / "dataspec.json",
        chart_dir / "metadata.json",
        chart_dir / "artifacts/chart.png",
        chart_dir / "artifacts/code.py",
        chart_dir / "data/raw.csv"
    ]

    for f in required_files:
        if not f.exists():
            raise FileNotFoundError(f"缺少必要文件: {f}")

    # 2. 加载元数据
    dataspec = load_json(chart_dir / "dataspec.json")
    metadata = load_json(chart_dir / "metadata.json")
    code = load_text(chart_dir / "artifacts/code.py")
    raw_csv_path = chart_dir / "data/raw.csv"

    # 3. 判断数据类型
    data_type = classify_data_type(dataspec, metadata)
    data_points = metadata.get('data_source', {}).get('data_points', 0)

    print(f"   📊 数据类型: {data_type.value}, 数据点数: {data_points}")

    # 4. 生成数据摘要
    if data_type in [DataType.TIME_SERIES_LONG, DataType.TIME_SERIES_SHORT]:
        data_summary = process_time_series(
            raw_csv_path,
            data_points,
            max_raw=MAX_RAW_POINTS
        )
    else:
        data_summary = process_cross_section(
            raw_csv_path,
            data_points,
            max_raw=MAX_RAW_POINTS,
            head_tail=MAX_HEAD_TAIL
        )

    print(f"   📝 数据摘要长度: {len(data_summary)} 字符")

    # 5. 构建提示词
    user_prompt = build_prompt(
        dataspec=dataspec,
        metadata=metadata,
        data_summary=data_summary,
        code=code
    )

    # 6. 编码图片
    image_path = chart_dir / "artifacts/chart.png"
    base64_image = encode_image(image_path)
    image_size_kb = len(base64_image) // 1024

    print(f"   🖼️  图片大小: {image_size_kb} KB")

    # 7. 调用 API
    print(f"   🤖 调用模型: {model}")
    start_time = datetime.now()

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                            "detail": "high"
                        }
                    },
                    {
                        "type": "text",
                        "text": user_prompt
                    }
                ]
            }
        ],
        max_completion_tokens=4096
    )

    duration = (datetime.now() - start_time).total_seconds()
    analysis = completion.choices[0].message.content or ""

    print(f"   ✅ 完成，耗时: {duration:.2f}s, 分析长度: {len(analysis)} 字符")

    # 8. 组装结果
    result = {
        "chart_id": chart_dir.name,
        "analysis": analysis,
        "metadata": {
            "chart_type": dataspec.get('chart_type'),
            "data_type": data_type.value,
            "data_points": data_points,
            "data_source": dataspec.get('what', {}).get('data_source'),
            "time_range": metadata.get('data_source', {}).get('time_range'),
            "language": dataspec.get('language')
        },
        "processing": {
            "model": model,
            "duration_s": round(duration, 2),
            "image_size_kb": image_size_kb,
            "data_summary_len": len(data_summary),
            "api_usage": {
                "prompt_tokens": completion.usage.prompt_tokens if completion.usage else None,
                "completion_tokens": completion.usage.completion_tokens if completion.usage else None,
                "total_tokens": completion.usage.total_tokens if completion.usage else None
            }
        },
        "generated_at": datetime.now().isoformat()
    }

    # 9. 保存结果
    if output_path is None:
        output_path = chart_dir / "summary"

    output_path.mkdir(parents=True, exist_ok=True)

    # 保存分析文本
    with open(output_path / "analysis.txt", 'w', encoding='utf-8') as f:
        f.write(analysis)

    # 保存完整结果
    with open(output_path / "result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"   💾 结果已保存到: {output_path}")

    return result


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser(
        description="生成图表分析总结",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "chart_dir",
        type=Path,
        help="图表目录路径"
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="输出目录路径（默认为 chart_dir/summary）"
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"使用的模型（默认: {MODEL}）"
    )

    args = parser.parse_args()

    # 检查目录
    if not args.chart_dir.exists():
        print(f"❌ 目录不存在: {args.chart_dir}")
        return 1

    try:
        model = args.model or MODEL
        result = process_chart(args.chart_dir, args.output, model=model)
        print(f"\n✅ 处理完成!")
        return 0
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
