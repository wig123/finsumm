"""
横截面/面板数据处理器
====================
对于小数据量直接返回，大数据量使用头尾截断+统计摘要
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Union


def process_cross_section(
    csv_path: Union[str, Path],
    data_points: int,
    max_raw: int = 200,
    head_tail: int = 50
) -> str:
    """
    处理横截面/面板数据

    Args:
        csv_path: CSV 文件路径
        data_points: 数据点数
        max_raw: 直接返回原始数据的阈值
        head_tail: 截断时头尾各取多少条

    Returns:
        数据摘要字符串
    """
    df = pd.read_csv(csv_path)

    if data_points <= max_raw:
        # 短数据：直接返回
        return f"[原始数据 - {len(df)} 条]\n{df.to_string(index=False)}"

    # 长数据：截断 + 统计摘要
    return generate_cs_summary(df, head_tail)


def generate_cs_summary(df: pd.DataFrame, head_tail: int = 50) -> str:
    """
    生成横截面数据摘要

    Args:
        df: 数据框
        head_tail: 头尾各取多少条

    Returns:
        格式化的摘要字符串
    """
    sections = []
    n_rows = len(df)

    # ========== 1. 基本信息 ==========
    sections.append(f"[基本信息]\n数据行数: {n_rows}\n列名: {', '.join(df.columns.tolist())}")

    # ========== 2. 数值列统计 ==========
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if numeric_cols:
        stats_lines = []
        for col in numeric_cols[:5]:  # 最多5列
            s = df[col].describe()
            stats_lines.append(
                f"  {col}: min={s['min']:.4g}, max={s['max']:.4g}, "
                f"mean={s['mean']:.4g}, std={s['std']:.4g}"
            )
        sections.append("[数值列统计]\n" + "\n".join(stats_lines))

    # ========== 3. 分类列分布 ==========
    cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    if cat_cols:
        dist_lines = []
        for col in cat_cols[:3]:  # 最多3列
            vc = df[col].value_counts()
            n_unique = len(vc)
            if n_unique <= 10:
                top_items = ", ".join([f"{k}({v})" for k, v in vc.items()])
            else:
                top_items = ", ".join([f"{k}({v})" for k, v in vc.head(5).items()]) + f" ...共{n_unique}类"
            dist_lines.append(f"  {col}: {top_items}")
        sections.append("[分类列分布]\n" + "\n".join(dist_lines))

    # ========== 4. 头部数据 ==========
    head_df = df.head(head_tail)
    sections.append(f"[头部数据 - 前{len(head_df)}条]\n{head_df.to_string(index=False)}")

    # ========== 5. 尾部数据（如果总行数够大）==========
    if n_rows > head_tail * 2:
        tail_df = df.tail(head_tail)
        sections.append(f"[尾部数据 - 后{len(tail_df)}条]\n{tail_df.to_string(index=False)}")

    return "\n\n".join(sections)
