"""Coder LLM的输入输出模型"""
from typing import Dict, Any
from pydantic import BaseModel


class CoderInput(BaseModel):
    """Coder输入"""
    library: str
    chart_type: str
    language_config: Dict[str, Any]
    dataframe_head: str
    annotations: list
    error_context: str | None = None  # 重试时的错误信息


class CoderOutput(BaseModel):
    """Coder输出"""
    code: str
    explanation: str | None = None
