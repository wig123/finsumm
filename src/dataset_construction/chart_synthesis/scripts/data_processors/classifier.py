"""
数据类型分类器
"""

from enum import Enum
from typing import Dict, Any


class DataType(Enum):
    """数据类型枚举"""
    TIME_SERIES_SHORT = "time_series_short"   # 短时间序列 (≤200)
    TIME_SERIES_LONG = "time_series_long"     # 长时间序列 (>200)
    CROSS_SECTION_SHORT = "cross_section_short"  # 短横截面 (≤200)
    CROSS_SECTION_LONG = "cross_section_long"    # 长横截面 (>200)


# 时间序列 shape 标识
TIME_SERIES_SHAPES = {
    'TS_1D',    # 一维时间序列
    'TS_ND',    # 多维时间序列
    'TS',       # 通用时间序列
}

# 横截面/矩阵 shape 标识
CROSS_SECTION_SHAPES = {
    'MATRIX',   # 矩阵
    'CS',       # 横截面
    'CS_1D',    # 一维横截面
    'CS_ND',    # 多维横截面
    'PANEL',    # 面板数据
}


def classify_data_type(
    dataspec: Dict[str, Any],
    metadata: Dict[str, Any],
    threshold: int = 200
) -> DataType:
    """
    根据 dataspec 和 metadata 判断数据类型

    Args:
        dataspec: 数据规格 JSON
        metadata: 元数据 JSON
        threshold: 长短数据的阈值（默认 200）

    Returns:
        DataType 枚举值
    """
    # 获取 shape 和数据点数
    shape = dataspec.get('shape', '').upper()
    data_points = metadata.get('data_source', {}).get('data_points', 0)

    # 判断是否为时间序列
    is_time_series = False

    # 1. 优先根据 shape 判断
    if shape in TIME_SERIES_SHAPES:
        is_time_series = True
    elif shape in CROSS_SECTION_SHAPES:
        is_time_series = False
    else:
        # 2. 根据图表类型推断
        chart_type = dataspec.get('chart_type', '').lower()

        # 典型时间序列图表
        ts_chart_types = {
            'line', 'area', 'candlestick', 'ohlc', 'kline',
            'bollinger_bands', 'ichimoku_cloud', 'renko',
            'candlestick_volume', 'candlestick_indicator',
            'line_band_overlay', 'fan_chart'
        }

        # 典型横截面图表
        cs_chart_types = {
            'bar', 'pie', 'donut', 'treemap', 'sunburst',
            'heatmap', 'scatter', 'bubble', 'radar',
            'histogram', 'box', 'violin', 'density'
        }

        if chart_type in ts_chart_types:
            is_time_series = True
        elif chart_type in cs_chart_types:
            is_time_series = False
        else:
            # 3. 根据 when 配置推断
            when = dataspec.get('when', {})
            frequency = when.get('frequency', '')

            # 有明确频率的通常是时间序列
            if frequency in ['D', 'W', 'M', 'Q', 'Y', 'H', 'T']:
                is_time_series = True

    # 根据数据点数判断长短
    is_long = data_points > threshold

    if is_time_series:
        return DataType.TIME_SERIES_LONG if is_long else DataType.TIME_SERIES_SHORT
    else:
        return DataType.CROSS_SECTION_LONG if is_long else DataType.CROSS_SECTION_SHORT
