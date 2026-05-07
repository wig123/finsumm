"""
数据处理器模块
==============
根据数据类型生成适合 LLM 的数据摘要
"""

from .classifier import DataType, classify_data_type
from .time_series import process_time_series
from .cross_section import process_cross_section

__all__ = [
    'DataType',
    'classify_data_type',
    'process_time_series',
    'process_cross_section'
]
