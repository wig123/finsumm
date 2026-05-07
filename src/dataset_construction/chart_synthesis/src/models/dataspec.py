"""DataSpec数据模型 - 六维正交结构"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


class DataShape(str, Enum):
    """数据形态枚举"""
    TS_1D = "TS_1D"  # 单变量时序
    TS_ND = "TS_ND"  # 多变量时序
    CS_1D = "CS_1D"  # 单变量横截面
    CS_ND = "CS_ND"  # 多变量横截面
    MATRIX = "MATRIX"  # 矩阵


class WhatDimension(BaseModel):
    """What维度 - 测量对象"""
    indicator_id: str
    data_source: str
    series_code: str


class WhereDimension(BaseModel):
    """Where维度 - 测量范围"""
    entity_type: str
    entities: List[str]


class TimeRange(BaseModel):
    """时间区间"""
    type: str  # "relative" | "absolute"
    lookback: Optional[str] = None  # "20Y", "1M"
    start: Optional[str] = None
    end: Optional[str] = None


class WhenDimension(BaseModel):
    """When维度 - 时间维度"""
    range: TimeRange
    frequency: str  # "D", "W", "M", "Q", "Y"


class HowDimension(BaseModel):
    """How维度 - 数据变换"""
    transform: List[str]
    adjustments: List[str] = Field(default_factory=list)
    unit: str


class TSPolicy(BaseModel):
    """时序数据Payload策略"""
    max_points_raw: int = 200
    max_horizon_raw: str = "30D"
    repr_id: str = "ts_profile_v1"
    include_recent_raw: str = "30D"


class CSPolicy(BaseModel):
    """横截面数据Payload策略"""
    max_items_raw: int = 500
    repr_id: Optional[str] = None


class LLMPayloadPolicy(BaseModel):
    """LLM数据暴露策略"""
    mode: str = "auto"  # "auto" | "raw_only" | "repr_only" | "raw_and_repr"
    ts_policy: TSPolicy = Field(default_factory=TSPolicy)
    cs_policy: CSPolicy = Field(default_factory=CSPolicy)


class LibraryConfig(BaseModel):
    """绘图库配置"""
    python_lib: str
    frontend_lib: str
    tier: int
    weight: float


class FontSettings(BaseModel):
    """字体设置"""
    family: List[str]
    size: int = 10


class LanguageConfig(BaseModel):
    """语言配置"""
    locale: str  # "zh-CN" | "en-US"
    labels: Dict[str, Any]  # {"title": "...", "x_label": "...", "y_label": "...", "legend": [...]}
    font_settings: FontSettings


class OutputConfig(BaseModel):
    """输出配置"""
    pass  # 预留扩展


class DataSpec(BaseModel):
    """完整DataSpec - 六维正交结构"""
    # 输入侧指定
    chart_type: str
    language: str

    # 六维
    shape: DataShape
    what: WhatDimension
    where: WhereDimension
    when: WhenDimension
    how: HowDimension

    # 配置
    library_config: LibraryConfig
    language_config: LanguageConfig
    llm_payload_policy: LLMPayloadPolicy
    output: OutputConfig

    # 视觉风格（可选，默认为 default）
    visual_style: str = "default"

    # Planner 生成的业务问题（用于合成数据生成）
    question: Optional[str] = None

    class Config:
        use_enum_values = True
