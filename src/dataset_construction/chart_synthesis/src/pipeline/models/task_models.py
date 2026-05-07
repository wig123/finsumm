"""任务数据模型 v2"""

from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class TaskDefinition:
    """任务定义 v2 - 包含预选的 indicator"""
    task_id: str
    chart_type: str
    language: str
    theme: str
    visual_style: str
    batch_index: int
    # v2 新增：预选的数据配置
    indicator: str
    data_source: str
    indicator_description_zh: str
    indicator_description_en: str
    shape: str = "TS_1D"  # 数据形态
    is_frontend: bool = False
    # v2.1 新增：时间范围配置
    time_range_years: Optional[int] = None  # 时间范围（年）
    time_window_start: Optional[str] = None  # 时间窗口起始日期 (YYYY-MM-DD)
    time_window_end: Optional[str] = None    # 时间窗口结束日期 (YYYY-MM-DD)


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    status: str  # completed, failed
    chart_id: Optional[str] = None
    output_dir: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    retry_count: int = 0
    timestamp: str = ""
    summary_generated: bool = False
