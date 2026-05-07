"""DataSpec编译器 - 规范化编译层"""
import logging
from typing import Dict, Any

from ...models.dataspec import (
    DataSpec, DataShape, WhatDimension, WhereDimension,
    WhenDimension, HowDimension, LLMPayloadPolicy,
    LibraryConfig, LanguageConfig, OutputConfig,
    TimeRange, FontSettings
)
from ...models.planner_models import PlannerInput, PlannerOutput
from ...utils.config_loader import (
    load_chart_mapping,
    load_data_source_mapping,
    load_pipeline_config
)

logger = logging.getLogger(__name__)


class DataSpecCompilationError(Exception):
    """DataSpec编译错误"""
    pass


class DataSpecCompiler:
    """DataSpec编译器"""

    # 支持 OHLC 数据的数据源列表（按稳定性排序：yfinance 最稳定）
    OHLC_DATA_SOURCES = ['yfinance', 'efinance', 'baostock']

    def __init__(self):
        self.chart_mapping = load_chart_mapping()["chart_types"]
        self.data_source_mapping = load_data_source_mapping()
        self.pipeline_config = load_pipeline_config()

    def compile(
        self,
        planner_input: PlannerInput,
        planner_output: PlannerOutput
    ) -> DataSpec:
        """编译DataSpec

        Args:
            planner_input: Planner输入
            planner_output: Planner输出

        Returns:
            完整DataSpec
        """
        logger.info(f"开始编译DataSpec: {planner_input.chart_type}")

        # 1. 查询图表库映射（支持用户指定library和is_frontend）
        library_config = self._get_library_config(
            planner_input.chart_type,
            planner_input.library,
            planner_input.is_frontend
        )

        # 2. 配置字体设置
        language_config = self._build_language_config(
            planner_input.language,
            planner_output.labels
        )

        # 3. 映射数据源（检查OHLC要求）
        data_source = planner_output.data_requirement.data_source
        indicator = planner_output.data_requirement.indicator

        # 检查图表类型是否需要 OHLC 数据
        if self._requires_ohlc_data(planner_input.chart_type):
            data_source, indicator = self._ensure_ohlc_data_source(
                data_source, indicator, planner_input.chart_type
            )

        what_dimension = self._build_what_dimension(indicator, data_source)

        # 4. 推断数据形态
        shape = self._infer_shape(
            planner_output.data_requirement.shape,
            planner_input.chart_type,
            planner_output.data_requirement.entities
        )

        # 5. 构建其他维度
        where_dimension = WhereDimension(
            entity_type="country",  # 简化处理,后续可扩展
            entities=planner_output.data_requirement.entities
        )

        when_dimension = self._build_when_dimension(
            planner_output.data_requirement.time_horizon,
            planner_output.data_requirement.frequency
        )

        how_dimension = HowDimension(
            transform=[planner_output.data_requirement.transform],
            adjustments=[],
            unit="pct" if "pct" in planner_output.data_requirement.transform else "value"
        )

        # 6. 构建LLM Payload策略
        llm_payload_policy = self._build_payload_policy(shape)

        # 7. 输出配置
        output_config = OutputConfig()

        # 8. 获取视觉风格（默认为default）
        visual_style = getattr(planner_input, 'visual_style', 'default')

        # 9. 组装DataSpec
        dataspec = DataSpec(
            chart_type=planner_input.chart_type,
            language=planner_input.language,
            shape=shape,
            what=what_dimension,
            where=where_dimension,
            when=when_dimension,
            how=how_dimension,
            library_config=library_config,
            language_config=language_config,
            llm_payload_policy=llm_payload_policy,
            output=output_config,
            visual_style=visual_style,
            question=planner_output.question  # 传递业务问题用于合成数据生成
        )

        logger.info(f"DataSpec编译完成: shape={shape}, library={library_config.python_lib}, style={visual_style}")
        return dataspec

    def _get_library_config(
        self,
        chart_type: str,
        library: str = None,
        is_frontend: bool = False
    ) -> LibraryConfig:
        """获取图表库配置

        Args:
            chart_type: 图表类型
            library: 可选指定的库，如果为None则使用默认库
            is_frontend: 是否使用前端库

        Returns:
            LibraryConfig
        """
        if chart_type not in self.chart_mapping:
            raise DataSpecCompilationError(
                f"未知图表类型: {chart_type}. "
                f"可用类型: {list(self.chart_mapping.keys())}"
            )

        mapping = self.chart_mapping[chart_type]

        # 获取支持的Python库列表（兼容旧格式python_lib和新格式python_libs）
        if "python_libs" in mapping:
            supported_python_libs = mapping["python_libs"]
            default_python_lib = supported_python_libs[0]
        else:
            # 兼容旧格式
            supported_python_libs = [mapping["python_lib"]]
            default_python_lib = mapping["python_lib"]

        # 获取支持的前端库列表
        if "frontend_libs" in mapping:
            supported_frontend_libs = mapping["frontend_libs"]
            default_frontend_lib = supported_frontend_libs[0]
        elif "frontend_lib" in mapping:
            # 兼容旧格式
            supported_frontend_libs = [mapping["frontend_lib"]]
            default_frontend_lib = mapping["frontend_lib"]
        else:
            supported_frontend_libs = []
            default_frontend_lib = ""

        # 确定使用的库
        if is_frontend:
            # 前端模式
            if library:
                if library not in supported_frontend_libs:
                    logger.warning(
                        f"指定的前端库 {library} 不在 {chart_type} 支持列表 {supported_frontend_libs} 中，"
                        f"使用默认库 {default_frontend_lib}"
                    )
                    frontend_lib = default_frontend_lib
                else:
                    frontend_lib = library
            else:
                frontend_lib = default_frontend_lib
            python_lib = default_python_lib  # 前端模式下python_lib仍保留默认值

        else:
            # Python模式
            if library:
                if library not in supported_python_libs:
                    logger.warning(
                        f"指定的库 {library} 不在 {chart_type} 支持列表 {supported_python_libs} 中，"
                        f"使用默认库 {default_python_lib}"
                    )
                    python_lib = default_python_lib
                else:
                    python_lib = library
            else:
                python_lib = default_python_lib
            frontend_lib = default_frontend_lib

        return LibraryConfig(
            python_lib=python_lib,
            frontend_lib=frontend_lib,
            tier=mapping["tier"],
            weight=mapping["weight"]
        )

    def _build_language_config(
        self,
        language: str,
        labels: Dict[str, Any]
    ) -> LanguageConfig:
        """构建语言配置"""
        # 获取字体设置
        lang_config = self.pipeline_config["language"].get(language, {})
        fonts = lang_config.get("fonts", ["DejaVu Sans", "Arial"])

        return LanguageConfig(
            locale=language,
            labels=labels.dict() if hasattr(labels, 'dict') else labels,
            font_settings=FontSettings(family=fonts, size=10)
        )

    def _build_what_dimension(
        self,
        indicator: str,
        data_source: str
    ) -> WhatDimension:
        """构建What维度"""
        # 处理逗号分隔的数据源(如"FRED, Synthetic"),取第一个
        if ',' in data_source:
            data_source = data_source.split(',')[0].strip()
            logger.info(f"检测到多个数据源,使用第一个: {data_source}")

        # 映射indicator到series_code
        source_mapping = self.data_source_mapping.get(data_source.lower(), {})

        # 处理逗号分隔的多个指标
        if ',' in indicator:
            indicators = [ind.strip() for ind in indicator.split(',')]
            series_codes = []
            unmapped_indicators = []

            for ind in indicators:
                if ind not in source_mapping:
                    unmapped_indicators.append(ind)
                    series_codes.append(ind)  # 使用原始indicator
                else:
                    mapped_value = source_mapping[ind]
                    # 如果映射值是字典(带func和params),保留原始indicator供Adapter查找
                    if isinstance(mapped_value, dict):
                        series_codes.append(ind)
                    else:
                        series_codes.append(mapped_value)

            if unmapped_indicators:
                logger.warning(
                    f"指标{', '.join(unmapped_indicators)}未在{data_source}映射表中找到,使用原始indicator"
                )

            series_code = ', '.join(series_codes)
        else:
            # 单个指标
            if indicator not in source_mapping:
                logger.warning(
                    f"指标{indicator}未在{data_source}映射表中找到,使用原始indicator"
                )
                series_code = indicator
            else:
                mapped_value = source_mapping[indicator]
                # 如果映射值是字典(带func和params),保留原始indicator供Adapter查找
                if isinstance(mapped_value, dict):
                    series_code = indicator
                    logger.info(f"指标{indicator}使用复杂映射配置,保留indicator作为series_code")
                else:
                    series_code = mapped_value

        return WhatDimension(
            indicator_id=indicator,
            data_source=data_source,
            series_code=series_code
        )

    def _infer_shape(
        self,
        requested_shape: str,
        chart_type: str,
        entities: list
    ) -> DataShape:
        """推断数据形态"""
        # 优先使用Planner指定的shape
        if requested_shape:
            try:
                return DataShape(requested_shape)
            except ValueError:
                logger.warning(f"无效的shape: {requested_shape}, 将自动推断")

        # 自动推断
        if chart_type in ["line", "candlestick", "area"]:
            return DataShape.TS_ND if len(entities) > 1 else DataShape.TS_1D
        elif chart_type in ["bar", "pie", "scatter"]:
            return DataShape.CS_ND if len(entities) > 1 else DataShape.CS_1D
        elif chart_type in ["heatmap"]:
            return DataShape.MATRIX
        else:
            return DataShape.TS_1D  # 默认

    def _build_when_dimension(
        self,
        time_horizon: str,
        frequency: str
    ) -> WhenDimension:
        """构建When维度"""
        return WhenDimension(
            range=TimeRange(
                type="relative",
                lookback=time_horizon
            ),
            frequency=frequency
        )

    def _build_payload_policy(self, shape: DataShape) -> LLMPayloadPolicy:
        """构建LLM Payload策略"""
        policy_config = self.pipeline_config["llm_payload_policy"]

        if shape in [DataShape.TS_1D, DataShape.TS_ND]:
            from ...models.dataspec import TSPolicy
            ts_config = policy_config["time_series"]
            ts_policy = TSPolicy(
                max_points_raw=ts_config["max_points_raw"],
                max_horizon_raw=ts_config["max_horizon_raw"],
                repr_id=ts_config["repr_method"],
                include_recent_raw=ts_config["include_recent_raw"]
            )
            return LLMPayloadPolicy(mode="auto", ts_policy=ts_policy)
        else:
            from ...models.dataspec import CSPolicy
            cs_config = policy_config["cross_sectional"]
            cs_policy = CSPolicy(
                max_items_raw=cs_config["max_items_raw"],
                repr_id=cs_config["repr_method"]
            )
            return LLMPayloadPolicy(mode="auto", cs_policy=cs_policy)

    def _requires_ohlc_data(self, chart_type: str) -> bool:
        """检查图表类型是否需要 OHLC 数据

        Args:
            chart_type: 图表类型

        Returns:
            是否需要 OHLC 数据
        """
        if chart_type not in self.chart_mapping:
            return False

        mapping = self.chart_mapping[chart_type]
        required_shapes = mapping.get("required_shapes", [])

        return "TS_OHLC" in required_shapes

    def _ensure_ohlc_data_source(
        self,
        data_source: str,
        indicator: str,
        chart_type: str
    ) -> tuple:
        """确保使用支持 OHLC 的数据源

        如果当前数据源不支持 OHLC，抛出明确错误，不进行静默替换。

        Args:
            data_source: 原始数据源
            indicator: 原始指标ID
            chart_type: 图表类型

        Returns:
            (数据源, 指标ID) 元组

        Raises:
            DataSpecCompilationError: 如果数据源不支持 OHLC
        """
        # 处理逗号分隔的数据源，取第一个
        if ',' in data_source:
            data_source = data_source.split(',')[0].strip()

        # 如果已经是支持 OHLC 的数据源，直接返回
        if data_source.lower() in self.OHLC_DATA_SOURCES:
            logger.info(f"数据源 {data_source} 支持 OHLC，验证通过")
            return data_source, indicator

        # 当前数据源不支持 OHLC，抛出错误
        error_msg = (
            f"图表类型 '{chart_type}' 需要 OHLC 四价数据 (开盘/最高/最低/收盘)，"
            f"但 Planner 选择的数据源 '{data_source}' 不支持 OHLC。\n"
            f"支持 OHLC 的数据源: {', '.join(self.OHLC_DATA_SOURCES)}\n"
            f"原始指标: {indicator}\n\n"
            f"【原因分析】\n"
            f"- FRED 数据源只提供单值时序数据，无法获取 OHLC 四价\n"
            f"- Planner 可能错误地为 OHLC 图表类型选择了不兼容的数据源\n\n"
            f"【解决方案】\n"
            f"1. 检查 Planner 的图表类型约束是否生效\n"
            f"2. 确保 prompts 中明确禁止 OHLC 图表使用 FRED\n"
            f"3. 如果是商品数据，应使用 yfinance (如 CL=F 原油期货)"
        )
        
        logger.error(error_msg)
        raise DataSpecCompilationError(error_msg)
