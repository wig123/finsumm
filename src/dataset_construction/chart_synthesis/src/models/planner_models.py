"""Planner LLM的输入输出模型"""
from typing import Dict, List, Optional, Literal, Union
from pydantic import BaseModel, Field, field_validator


# 允许的主题和任务枚举（20个金融主题 - 对齐 FinanceTopics.v1）
ALLOWED_THEMES = [
    "macro_policy",
    "fiscal_policy",
    "inflation",
    "growth_employment",
    "fx_trade",
    "equity_markets",
    "fixed_income",
    "commodities",
    "derivatives",
    "digital_assets",
    "banking_credit",
    "insurance",
    "asset_management",
    "real_estate",
    "corporate_finance",
    "ma_ipos",
    "payments_fintech",
    "risk_regulation",
    "accounting_reporting",
    "esg_sustainable"
]

# 允许的视觉风格枚举（8种金融图表视觉风格）
ALLOWED_VISUAL_STYLES = [
    "trading",    # 交易终端风
    "quant",      # 量化学术风
    "macro",      # 宏观国际风
    "news",       # 新闻媒体风
    "corporate",  # 企业财报风
    "fintech",    # Fintech应用风
    "regulator",  # 监管央行风
    "research",   # 机构研报风
    "default"     # 默认专业风格
]


class PlannerInput(BaseModel):
    """Planner输入"""
    chart_type: str
    language: str  # "zh-CN" | "en-US"
    theme: str  # 必须是 ALLOWED_THEMES 之一
    library: Optional[str] = None  # 可选指定绑图库，如不指定则使用默认库
    is_frontend: bool = False  # 是否使用前端库渲染，True 则使用 frontend_libs
    visual_style: str = "default"  # 视觉风格，必须是 ALLOWED_VISUAL_STYLES 之一
    data_constraints: Optional[Dict] = Field(default_factory=dict)

    @field_validator('visual_style')
    @classmethod
    def validate_visual_style(cls, v):
        if v not in ALLOWED_VISUAL_STYLES:
            raise ValueError(
                f"visual_style 必须是以下值之一: {ALLOWED_VISUAL_STYLES}, 得到: {v}"
            )
        return v

    @field_validator('theme')
    @classmethod
    def validate_theme(cls, v):
        if v not in ALLOWED_THEMES:
            raise ValueError(
                f"theme 必须是以下值之一: {ALLOWED_THEMES}, 得到: {v}"
            )
        return v


class DataRequirement(BaseModel):
    """数据需求"""
    indicator: Union[str, List[str]]  # 支持单个指标或多个指标列表
    entities: List[str]
    time_horizon: str
    frequency: str
    transform: str
    shape: str
    data_source: str

    @field_validator('indicator', mode='before')
    @classmethod
    def normalize_indicator(cls, v):
        """将列表转换为逗号分隔的字符串"""
        if isinstance(v, list):
            return ', '.join(v)
        return v

    @field_validator('transform', mode='before')
    @classmethod
    def normalize_transform(cls, v):
        """强制转换transform为字符串

        LLM可能输出dict(如{"type": "pct_change"})或int,统一转为string
        """
        if isinstance(v, dict):
            # 如果是dict,提取type字段或转为JSON字符串
            return v.get('type', str(v))
        return str(v)


class Labels(BaseModel):
    """图表标签"""
    title: str
    x_label: str
    y_label: str
    legend: Optional[List[str]] = None


class PlannerOutput(BaseModel):
    """Planner输出"""
    question: str
    data_requirement: DataRequirement
    labels: Labels
