"""任务生成器 v2 - 程序化数据选择"""

import random
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Any

from ..models import TaskDefinition
from .quota_loader import QuotaLoader

logger = logging.getLogger(__name__)


# 图表类型分类
OHLC_CHARTS = {'candlestick', 'ohlc_bar'}  # 需要 OHLC 数据
VOLUME_REQUIRED_CHARTS = {'candlestick', 'ohlc_bar'}  # 需要成交量
TS_CHARTS = {'line', 'area', 'sparkline', 'multi_line'}  # 普通时序
CS_ND_REQUIRED_CHARTS = {'grouped_bar', 'stacked_bar', 'multi_line', 'radar'}  # 需要多变量
CS_1D_REQUIRED_CHARTS = {'bar', 'pie', 'donut', 'treemap', 'waterfall', 'gauge'}  # 单变量横截面
MATRIX_REQUIRED_CHARTS = {'heatmap'}  # 需要矩阵
FLEXIBLE_CHARTS = {'scatter', 'bubble'}  # 灵活
SPECIAL_CHARTS = {'funnel', 'sankey'}  # 特殊


class TaskGenerator:
    """任务生成器 v2 - 程序化数据选择"""

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)
        self.quota_loader = QuotaLoader()
        self.config = self.quota_loader.load()

    def generate(self, total: int = 1000, batch_size: int = 200) -> List[TaskDefinition]:
        """生成任务列表"""
        tasks = []
        constraints = self.config['constraints']
        chart_mapping = self.config['chart_mapping']

        # 指标映射来自 constraints 中的 theme_indicator_mapping
        theme_indicator_mapping = constraints.get('theme_indicator_mapping', {})

        # 从 chart_library_mapping 提取图表类型权重
        chart_types_config = chart_mapping.get('chart_types', {})
        chart_quotas = {k: v.get('weight', 0.01) for k, v in chart_types_config.items()}

        # 从 theme_indicator_mapping 生成主题概率（均匀分布）
        theme_probs = {t: 1.0/len(theme_indicator_mapping) for t in theme_indicator_mapping} if theme_indicator_mapping else {'macro_policy': 1.0}

        style_probs = constraints.get('visual_style_quota', {})
        if not style_probs:
            style_probs = {'default': 0.5, 'minimalist': 0.3, 'professional': 0.2}

        lang_probs = constraints.get('language_quota', {'zh-CN': 0.5, 'en-US': 0.5})
        hard_constraints = constraints.get('hard_constraints', {})
        affinity = constraints.get('chart_theme_affinity', {})

        # 按配额分配图表类型
        chart_assignments = self._distribute_charts(chart_quotas, total)

        for i, chart_type in enumerate(chart_assignments):
            batch_idx = i // batch_size

            # 选择主题（带亲和度）
            theme = self._select_theme_for_chart(chart_type, theme_probs, affinity, hard_constraints)

            # 选择视觉风格（带亲和度）
            style = self._select_style_for_theme(theme, chart_type, style_probs, affinity, hard_constraints)

            # 选择语言
            language = self._weighted_choice(lang_probs)

            # 程序化选择 indicator（核心）
            theme_config = theme_indicator_mapping.get(theme, {})
            indicator_info = self._select_indicator(chart_type, theme, theme_config)

            # 选择时间范围（如果适用）
            time_config = self._select_time_range() if indicator_info['shape'].startswith('TS') else {}

            task = TaskDefinition(
                task_id=f"v2_{i:05d}",
                chart_type=chart_type,
                language=language,
                theme=theme,
                visual_style=style,
                batch_index=batch_idx,
                indicator=indicator_info['indicator'],
                data_source=indicator_info['data_source'],
                indicator_description_zh=indicator_info['description_zh'],
                indicator_description_en=indicator_info['description_en'],
                shape=indicator_info['shape'],
                time_range_years=time_config.get('years'),
                time_window_start=time_config.get('start'),
                time_window_end=time_config.get('end')
            )
            tasks.append(task)

        logger.info(f"生成 {len(tasks)} 个任务 (v2 程序化模式)")
        return tasks

    def _distribute_charts(self, chart_quotas: Dict[str, float], total: int) -> List[str]:
        """根据配额分配图表类型"""
        assignments = []

        # 计算每种图表的数量
        for chart_type, quota in chart_quotas.items():
            count = int(total * quota)
            assignments.extend([chart_type] * count)

        # 补齐缺口
        while len(assignments) < total:
            chart_type = random.choice(list(chart_quotas.keys()))
            assignments.append(chart_type)

        random.shuffle(assignments)
        return assignments[:total]

    def _select_indicator(self, chart_type: str, theme: str, theme_config: Dict) -> Dict:
        """程序化选择 indicator"""
        # OHLC 图表
        if chart_type in OHLC_CHARTS:
            ohlc_indicators = theme_config.get('ohlc_indicators', [])
            if ohlc_indicators:
                choice = random.choice(ohlc_indicators)
                return {
                    'indicator': choice['indicator'],
                    'data_source': choice['data_source'],
                    'description_zh': choice.get('description_zh', choice.get('indicator')),
                    'description_en': choice.get('description_en', choice.get('indicator')),
                    'shape': 'OHLC'
                }
            return self._synthetic_indicator(theme, theme_config, 'TS_1D')

        # 矩阵类型
        if chart_type in MATRIX_REQUIRED_CHARTS:
            return self._synthetic_indicator(theme, theme_config, 'MATRIX')

        # 多变量横截面
        if chart_type in CS_ND_REQUIRED_CHARTS:
            cs_nd_indicators = theme_config.get('cs_nd_indicators', [])
            if cs_nd_indicators:
                choice = random.choice(cs_nd_indicators)
                return {
                    'indicator': choice['indicator'],
                    'data_source': choice['data_source'],
                    'description_zh': choice.get('description_zh', choice.get('indicator')),
                    'description_en': choice.get('description_en', choice.get('indicator')),
                    'shape': 'CS_ND'
                }
            return self._synthetic_indicator(theme, theme_config, 'CS_ND')

        # 单变量横截面
        if chart_type in CS_1D_REQUIRED_CHARTS:
            cs_1d_indicators = theme_config.get('cs_1d_indicators', [])
            if cs_1d_indicators:
                choice = random.choice(cs_1d_indicators)
                return {
                    'indicator': choice['indicator'],
                    'data_source': choice['data_source'],
                    'description_zh': choice.get('description_zh', choice.get('indicator')),
                    'description_en': choice.get('description_en', choice.get('indicator')),
                    'shape': 'CS_1D'
                }
            return self._synthetic_indicator(theme, theme_config, 'CS_1D')

        # 特殊图表
        if chart_type in SPECIAL_CHARTS:
            return self._synthetic_indicator(theme, theme_config, 'FLOW')

        # 时序图表
        if chart_type in TS_CHARTS:
            indicators = theme_config.get('ts_indicators', [])
            if not indicators:
                ohlc_indicators = theme_config.get('ohlc_indicators', [])
                if ohlc_indicators:
                    indicators = ohlc_indicators

            if not indicators:
                raise ValueError(f"主题 {theme} 无可用指标用于 {chart_type}")

            choice = random.choice(indicators)
            return {
                'indicator': choice['indicator'],
                'data_source': choice['data_source'],
                'description_zh': choice.get('description_zh', choice.get('indicator')),
                'description_en': choice.get('description_en', choice.get('indicator')),
                'shape': 'TS_1D'
            }

        # 灵活图表
        if chart_type in FLEXIBLE_CHARTS:
            cs_nd_indicators = theme_config.get('cs_nd_indicators', [])
            if cs_nd_indicators:
                choice = random.choice(cs_nd_indicators)
                return {
                    'indicator': choice['indicator'],
                    'data_source': choice['data_source'],
                    'description_zh': choice.get('description_zh', choice.get('indicator')),
                    'description_en': choice.get('description_en', choice.get('indicator')),
                    'shape': 'CS_ND'
                }
            return self._synthetic_indicator(theme, theme_config, 'CS_ND')

        # 默认：时序
        indicators = theme_config.get('ts_indicators', [])
        if indicators:
            choice = random.choice(indicators)
            return {
                'indicator': choice['indicator'],
                'data_source': choice['data_source'],
                'description_zh': choice.get('description_zh', choice.get('indicator')),
                'description_en': choice.get('description_en', choice.get('indicator')),
                'shape': 'TS_1D'
            }
        return self._synthetic_indicator(theme, theme_config, 'TS_1D')

    def _select_time_range(self) -> Dict:
        """选择时间范围"""
        if random.random() < 0.50:
            # 固定时间范围长度
            years_options = [1, 2, 3, 5, 10, 20]
            years = random.choice(years_options)
            return {'years': years, 'start': None, 'end': None}
        else:
            # 随机历史窗口
            start_year = random.randint(1990, 2020)
            window_years = random.randint(3, 10)

            start_date = datetime(start_year, 1, 1)
            end_date = start_date + relativedelta(years=window_years)

            now = datetime.now()
            if end_date > now:
                end_date = now

            return {
                'years': None,
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }

    def _synthetic_indicator(self, theme: str, theme_config: Dict, required_shape: str = None) -> Dict:
        """生成合成数据指标"""
        if required_shape:
            shape = required_shape
        else:
            shapes = theme_config.get('synthetic_shapes', ['CS_1D'])
            shape = random.choice(shapes)

        shape_desc = {
            'CS_1D': '横截面单变量分布',
            'CS_ND': '横截面多变量比较',
            'MATRIX': '相关矩阵/热力图',
            'FLOW': '流向/归因',
            'GRAPH': '网络/图结构'
        }

        return {
            'indicator': f'synthetic.{theme}.{shape.lower()}',
            'data_source': 'Synthetic',
            'description_zh': f'{theme} {shape_desc.get(shape, "合成")}数据',
            'description_en': f'{theme} {shape} synthetic data',
            'shape': shape
        }

    def _weighted_choice(self, probs: Dict[str, float]) -> str:
        """加权随机选择"""
        items = list(probs.keys())
        weights = list(probs.values())
        return random.choices(items, weights=weights, k=1)[0]

    def _select_theme_for_chart(
        self,
        chart_type: str,
        theme_probs: Dict[str, float],
        affinity: Dict,
        hard_constraints: Dict
    ) -> str:
        """为图表类型选择合适的主题"""
        forbidden = set(hard_constraints.get('chart_forbidden_themes', {}).get(chart_type, []))

        chart_affinity = affinity.get(chart_type, {})
        default_affinity = chart_affinity.get('default', 0.5)

        weighted_probs = {}
        for theme, base_prob in theme_probs.items():
            if theme in forbidden:
                continue
            theme_affinity = chart_affinity.get(theme, default_affinity)
            if theme_affinity > 0:
                weighted_probs[theme] = base_prob * theme_affinity

        if not weighted_probs:
            weighted_probs = {k: v for k, v in theme_probs.items() if k not in forbidden}

        return self._weighted_choice(weighted_probs)

    def _select_style_for_theme(
        self,
        theme: str,
        chart_type: str,
        style_probs: Dict[str, float],
        affinity: Dict,
        hard_constraints: Dict
    ) -> str:
        """为主题选择合适的视觉风格"""
        forbidden_for_theme = set(
            k for k, v in hard_constraints.get('style_forbidden_themes', {}).items()
            if theme in v
        )
        forbidden_for_chart = set(
            k for k, v in hard_constraints.get('style_forbidden_charts', {}).items()
            if chart_type in v
        )
        forbidden = forbidden_for_theme | forbidden_for_chart

        weighted_probs = {}
        for style, base_prob in style_probs.items():
            if style in forbidden:
                continue
            style_affinity = affinity.get(style, {})
            theme_affinity = style_affinity.get(theme, style_affinity.get('default', 0.5))
            if theme_affinity > 0:
                weighted_probs[style] = base_prob * theme_affinity

        if not weighted_probs:
            weighted_probs = {'default': 1.0}

        return self._weighted_choice(weighted_probs)
