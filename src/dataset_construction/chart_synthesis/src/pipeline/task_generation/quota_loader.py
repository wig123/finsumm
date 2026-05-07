"""配额加载器"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class QuotaLoader:
    """加载配额配置（拆分后的结构）"""

    def __init__(self, config_dir: Path = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "config"
        self.config_dir = config_dir

    def _load_yaml(self, filename: str, required: bool = True) -> Dict:
        """加载单个 YAML 文件"""
        filepath = self.config_dir / filename
        if not filepath.exists():
            if required:
                raise FileNotFoundError(f"配置文件不存在: {filepath}")
            return {}
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def _load_indicators(self) -> Dict:
        """加载所有指标映射（从 indicators/*.yaml）"""
        indicators_dir = self.config_dir / "indicators"
        if not indicators_dir.exists():
            return {}

        all_indicators = {}
        for yaml_file in indicators_dir.glob("*.yaml"):
            data = self._load_yaml(f"indicators/{yaml_file.name}", required=False)
            all_indicators.update(data)
            logger.debug(f"加载指标配置: {yaml_file.name} ({len(data)} 个主题)")

        return all_indicators

    def load(self) -> Dict[str, Any]:
        """加载所有配额配置"""
        # 主配置（配额、硬约束）
        generation = self._load_yaml("generation.yaml")

        # 亲和度配置
        affinity = self._load_yaml("affinity.yaml", required=False)

        # 合并为 constraints
        constraints = {**generation, **affinity}

        # 加载指标映射
        theme_indicator_mapping = self._load_indicators()
        constraints['theme_indicator_mapping'] = theme_indicator_mapping

        # 图表库映射
        chart_mapping = self._load_yaml("chart_library_mapping.yaml")

        # 数据源映射
        ds_mapping = self._load_yaml("data_source_mapping.yaml", required=False)

        logger.info(f"配置加载完成: {len(theme_indicator_mapping)} 个主题, {len(chart_mapping.get('chart_types', {}))} 种图表")

        return {
            'constraints': constraints,
            'chart_mapping': chart_mapping,
            'data_source_mapping': ds_mapping
        }
