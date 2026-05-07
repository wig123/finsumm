"""元数据模型"""
from datetime import datetime
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field


class LLMExecutionInfo(BaseModel):
    """LLM执行信息"""
    model: str
    tokens: Optional[int] = None
    duration_ms: Optional[int] = None


class PipelineExecution(BaseModel):
    """Pipeline执行信息"""
    planner_llm: Optional[LLMExecutionInfo] = None
    coder_llm: Optional[LLMExecutionInfo] = None
    narrator_llm: Optional[LLMExecutionInfo] = None


class DataSourceInfo(BaseModel):
    """数据源信息"""
    source: str
    series_code: str
    time_range: str
    data_points: int


class QualityMetrics(BaseModel):
    """质量指标"""
    code_executable: bool
    image_generated: bool
    summary_length: Optional[int] = None


class ErrorInfo(BaseModel):
    """错误信息"""
    type: str
    message: str
    traceback: str


class ChartMetadata(BaseModel):
    """图表元数据"""
    chart_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    status: str  # "pending" | "in_progress" | "completed" | "failed"

    # 输入侧配置
    input_config: Dict[str, Any]

    # Pipeline执行信息
    pipeline_execution: PipelineExecution = Field(default_factory=PipelineExecution)

    # 数据源信息
    data_source: Optional[DataSourceInfo] = None

    # 质量指标
    quality_metrics: Optional[QualityMetrics] = None

    # 失败信息
    failed_at_layer: Optional[int] = None
    error: Optional[ErrorInfo] = None

    # 当前层级
    current_layer: int = 0

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
