"""配置加载工具"""
import yaml
from pathlib import Path
from typing import Dict, Any


def load_config(config_name: str) -> Dict[str, Any]:
    """加载配置文件

    Args:
        config_name: 配置文件名 (不含.yaml后缀)

    Returns:
        配置字典
    """
    config_path = Path(__file__).parent.parent.parent / "config" / f"{config_name}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_llm_config() -> Dict[str, Any]:
    """加载LLM配置"""
    return load_config("llm_config")


def load_chart_mapping() -> Dict[str, Any]:
    """加载图表库映射配置"""
    return load_config("chart_library_mapping")


def load_data_source_mapping() -> Dict[str, Any]:
    """加载数据源映射配置"""
    return load_config("data_source_mapping")


def load_pipeline_config() -> Dict[str, Any]:
    """加载Pipeline配置"""
    return load_config("pipeline_config")
