"""数据获取器"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
import pandas as pd

from ...models.dataspec import DataSpec, DataShape
from ...utils.retry_decorator import retry_on_failure
from .adapters import (
    FREDAdapter, 
    CrossSectionalAdapter,
    BaostockAdapter,
    YFinanceAdapter,
    EfinanceAdapter
)
from .synthetic_generator import SyntheticDataGenerator, SyntheticDataError

logger = logging.getLogger(__name__)


class DataFetchError(Exception):
    """数据获取错误"""
    pass


class DataFetcher:
    """数据获取器 - 从真实数据源获取数据或生成模拟数据"""

    # 需要 OHLC 数据的图表类型（不能降级到合成数据）
    OHLC_CHART_TYPES = [
        'candlestick', 'candlestick_volume', 'ohlc', 
        'bollinger_bands', 'ichimoku_cloud', 'renko', 
        'point_figure', 'candlestick_indicator'
    ]

    def __init__(self):
        """初始化数据获取器"""
        self.adapters = {
            # FRED - 美国宏观数据
            "FRED": FREDAdapter(),
            "fred": FREDAdapter(),
            
            # Baostock - A股指数（无限流、稳定）
            "Baostock": BaostockAdapter(),
            "baostock": BaostockAdapter(),
            
            # yfinance - 港股/全球指数/外汇
            "yfinance": YFinanceAdapter(),
            "YFinance": YFinanceAdapter(),
            
            # Efinance - 期货/ETF
            "Efinance": EfinanceAdapter(),
            "efinance": EfinanceAdapter(),
            
            # 横截面数据源
            "CrossSectional": CrossSectionalAdapter(),
            "cross_sectional": CrossSectionalAdapter(),
            "国家统计局": CrossSectionalAdapter(),
            "National Bureau of Statistics": CrossSectionalAdapter(),
            "IMF": CrossSectionalAdapter(),
            "世界银行": CrossSectionalAdapter(),
            "World Bank": CrossSectionalAdapter(),
            "FAOSTAT": CrossSectionalAdapter(),
            
            # 模拟数据
            "Synthetic": None,
            "synthetic": None,
        }
        
        # 初始化模拟数据生成器
        self.synthetic_generator = SyntheticDataGenerator()

    @retry_on_failure(max_retries=3, exceptions=(DataFetchError, Exception))
    def fetch(
        self,
        dataspec: DataSpec,
        question: Optional[str] = None
    ) -> Tuple[pd.DataFrame, bool]:
        """获取数据（真实数据或模拟数据）

        Args:
            dataspec: DataSpec
            question: 业务问题（模拟数据生成时使用）

        Returns:
            (DataFrame, is_synthetic) - is_synthetic 表示是否为模拟数据
        """
        # 1. 判断是否使用模拟数据
        use_synthetic = self._should_use_synthetic(dataspec)
        
        if use_synthetic:
            logger.info(f"使用模拟数据: {dataspec.chart_type}/{dataspec.shape}")
            if not question:
                question = f"生成{dataspec.chart_type}图表所需的{dataspec.shape}数据"
            df = self.synthetic_generator.generate_with_retry(dataspec, question)
            return df, True
        
        # 2. 使用真实数据
        logger.info(f"开始获取真实数据: {dataspec.what.data_source}/{dataspec.what.series_code}")

        # 选择适配器
        adapter = self._get_adapter(dataspec.what.data_source)

        # 判断是否为横截面数据
        is_cross_sectional = dataspec.shape in [DataShape.CS_1D, DataShape.CS_ND]

        # 检查数据源与数据形态的兼容性
        if is_cross_sectional and isinstance(adapter, FREDAdapter):
            raise DataFetchError(
                f"FRED数据源不支持横截面数据(shape={dataspec.shape})。"
                f"FRED仅提供时序数据,请使用CrossSectional或Synthetic数据源。"
            )

        if is_cross_sectional:
            # 横截面数据：传递 locale 和 entities
            locale = dataspec.language_config.locale if dataspec.language_config else 'zh-CN'
            entities = dataspec.where.entities if dataspec.where else None
            df = adapter.fetch(dataspec.what.series_code, locale=locale, entities=entities)
        else:
            # 时序数据需要计算时间范围
            start, end = self._compute_time_range(dataspec.when.range)
            df = adapter.fetch(dataspec.what.series_code, start, end)

        # 应用变换
        df = self._apply_transforms(df, dataspec)

        logger.info(f"真实数据获取成功: {len(df)}条数据点")
        return df, False
    
    def _should_use_synthetic(self, dataspec: DataSpec) -> bool:
        """判断是否应该使用模拟数据
        
        Args:
            dataspec: DataSpec
            
        Returns:
            True 表示应该使用模拟数据
        """
        # 如果数据源明确指定为 Synthetic，则使用模拟数据
        if dataspec.what.data_source in ["Synthetic", "synthetic"]:
            return True
        
        # 使用模拟数据生成器的判断逻辑
        return self.synthetic_generator.should_use_synthetic(dataspec)

    def fetch_and_build_payload(
        self,
        dataspec: DataSpec,
        question: Optional[str] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any], bool]:
        """获取数据并构建LLM Payload

        Args:
            dataspec: DataSpec
            question: 业务问题（模拟数据生成时使用）

        Returns:
            (DataFrame, llm_payload, is_synthetic)
        """
        # 获取数据
        df, is_synthetic = self.fetch(dataspec, question)

        # 构建Payload
        if dataspec.shape in [DataShape.TS_1D, DataShape.TS_ND]:
            llm_payload = self._build_ts_payload(df, dataspec)
        else:
            llm_payload = self._build_cs_payload(df, dataspec)
        
        # 如果是模拟数据，在 payload 中标记
        if is_synthetic:
            llm_payload["is_synthetic"] = True
            llm_payload["source"] = "LLM Generated Synthetic Data"

        return df, llm_payload, is_synthetic

    def _get_adapter(self, data_source: str):
        """获取数据源适配器"""
        if data_source not in self.adapters:
            raise DataFetchError(
                f"不支持的数据源: {data_source}. "
                f"支持: {list(self.adapters.keys())}"
            )
        return self.adapters[data_source]

    def _compute_time_range(self, time_range) -> Tuple[datetime, datetime]:
        """计算时间范围"""
        end = datetime.now()

        if time_range.type == "relative":
            # 解析lookback: "20Y", "5Y", "1M"
            lookback = time_range.lookback
            if lookback.endswith("Y"):
                years = int(lookback[:-1])
                start = end - timedelta(days=years * 365)
            elif lookback.endswith("M"):
                months = int(lookback[:-1])
                start = end - timedelta(days=months * 30)
            elif lookback.endswith("D"):
                days = int(lookback[:-1])
                start = end - timedelta(days=days)
            else:
                start = end - timedelta(days=365 * 5)  # 默认5年
        else:
            start = datetime.fromisoformat(time_range.start)
            end = datetime.fromisoformat(time_range.end)

        return start, end

    def _apply_transforms(self, df: pd.DataFrame, dataspec: DataSpec) -> pd.DataFrame:
        """应用数据变换"""
        for transform in dataspec.how.transform:
            if transform == "yoy_12m" or transform == "pct_change_12m":
                # 12个月同比
                df['value'] = df['value'].pct_change(12) * 100
            elif transform == "mom" or transform == "pct_change_1m":
                # 环比
                df['value'] = df['value'].pct_change(1) * 100
            elif transform == "level":
                # 保持原值
                pass

        # 删除NaN
        df = df.dropna()
        return df

    def _build_ts_payload(
        self,
        df: pd.DataFrame,
        dataspec: DataSpec
    ) -> Dict[str, Any]:
        """构建时序数据的LLM Payload"""
        policy = dataspec.llm_payload_policy.ts_policy
        n_points = len(df)

        # 计算时间跨度
        if len(df) > 0:
            time_span_days = self._compute_time_span_days(df, n_points)
        else:
            time_span_days = 0

        # 判断是否需要降维
        max_horizon_days = self._parse_duration(policy.max_horizon_raw)
        needs_repr = (n_points > policy.max_points_raw) or (time_span_days > max_horizon_days)

        if not needs_repr:
            # 短时序: 返回原始数据
            # 将 index (Timestamp) 转换为字符串以支持 JSON 序列化
            return {
                "type": "raw_series",
                "data": {str(k): v for k, v in df['value'].to_dict().items()}
            }
        else:
            # 长时序: 返回表征 + 最近N天原始
            repr_data = self._compute_ts_representation(df)

            # 最近N天原始数据
            recent_days = self._parse_duration(policy.include_recent_raw)
            recent_cutoff = df.index[-1] - timedelta(days=recent_days)
            recent_df = df[df.index >= recent_cutoff]

            return {
                "type": "repr_with_recent",
                "repr": repr_data,
                "recent_raw": {str(k): v for k, v in recent_df['value'].to_dict().items()}
            }

    def _build_cs_payload(
        self,
        df: pd.DataFrame,
        dataspec: DataSpec
    ) -> Dict[str, Any]:
        """构建横截面数据的LLM Payload"""
        policy = dataspec.llm_payload_policy.cs_policy

        if len(df) <= policy.max_items_raw:
            # 直接返回原始数据
            return {
                "type": "raw_table",
                "data": df.to_dict(orient="records")
            }
        else:
            # 返回top N
            df_top = df.head(policy.max_items_raw)
            return {
                "type": "top_items",
                "data": df_top.to_dict(orient="records"),
                "total_items": len(df)
            }

    def _compute_time_span_days(self, df: pd.DataFrame, n_points: int) -> int:
        """计算时间跨度（天数）
        
        Args:
            df: DataFrame，必须有索引
            n_points: 数据点数
            
        Returns:
            时间跨度（天数）
        """
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                # DatetimeIndex: 直接计算天数差
                return (df.index[-1] - df.index[0]).days
            else:
                # 尝试将索引转换为日期
                first_idx = pd.to_datetime(df.index[0])
                last_idx = pd.to_datetime(df.index[-1])
                return (last_idx - first_idx).days
        except Exception:
            # 无法转换时，根据数据点数估算（假设月度数据）
            estimated_days = n_points * 30
            logger.warning(
                f"索引无法解析为日期类型 (type={type(df.index).__name__})，"
                f"使用估算时间跨度: {estimated_days}天"
            )
            return estimated_days

    def _compute_ts_representation(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算时序表征"""
        values = df['value']

        # 安全获取索引值的字符串表示
        def safe_str(idx):
            if hasattr(idx, 'strftime'):
                return idx.strftime('%Y-%m-%d')
            return str(idx)

        return {
            "max_value": float(values.max()),
            "max_date": safe_str(values.idxmax()),
            "min_value": float(values.min()),
            "min_date": safe_str(values.idxmin()),
            "last_value": float(values.iloc[-1]),
            "last_date": safe_str(df.index[-1]),
            "mean": float(values.mean()),
            "std": float(values.std()),
            "n_points": len(df)
        }

    def _parse_duration(self, duration_str: str) -> int:
        """解析时间跨度字符串为天数"""
        if duration_str.endswith("D"):
            return int(duration_str[:-1])
        elif duration_str.endswith("M"):
            return int(duration_str[:-1]) * 30
        elif duration_str.endswith("Y"):
            return int(duration_str[:-1]) * 365
        else:
            return 30  # 默认30天

    async def fetch_async(
        self,
        dataspec: DataSpec,
        question: Optional[str] = None
    ) -> Tuple[pd.DataFrame, bool]:
        """异步获取数据（真实数据或模拟数据）

        Args:
            dataspec: DataSpec
            question: 业务问题（模拟数据生成时使用）

        Returns:
            (DataFrame, is_synthetic)
        """
        # 1. 判断是否使用模拟数据
        use_synthetic = self._should_use_synthetic(dataspec)
        
        if use_synthetic:
            logger.info(f"异步使用模拟数据: {dataspec.chart_type}/{dataspec.shape}")
            if not question:
                question = f"生成{dataspec.chart_type}图表所需的{dataspec.shape}数据"
            df = await self.synthetic_generator.generate_with_retry_async(dataspec, question)
            return df, True
        
        # 2. 尝试获取真实数据，失败时可能降级到合成数据
        try:
            df = await self._fetch_real_data_async(dataspec)
            logger.info(f"异步真实数据获取成功: {len(df)}条数据点")
            return df, False
        except Exception as e:
            # 检查是否可以降级到合成数据
            if self._can_fallback_to_synthetic(dataspec):
                logger.warning(
                    f"真实数据获取失败，降级到合成数据: {e}"
                )
                if not question:
                    question = f"生成{dataspec.chart_type}图表所需的{dataspec.shape}数据"
                df = await self.synthetic_generator.generate_with_retry_async(dataspec, question)
                return df, True
            else:
                # OHLC 图表不能降级，重新抛出异常
                logger.error(
                    f"真实数据获取失败，且图表类型 {dataspec.chart_type} 需要 OHLC 数据，无法降级: {e}"
                )
                raise

    def _can_fallback_to_synthetic(self, dataspec: DataSpec) -> bool:
        """检查是否可以降级到合成数据
        
        OHLC 图表类型不能降级，因为合成的 OHLC 数据没有意义。
        """
        return dataspec.chart_type not in self.OHLC_CHART_TYPES

    async def _fetch_real_data_async(self, dataspec: DataSpec) -> pd.DataFrame:
        """异步获取真实数据的内部方法"""
        logger.info(f"开始异步获取真实数据: {dataspec.what.data_source}/{dataspec.what.series_code}")

        # 选择适配器
        adapter = self._get_adapter(dataspec.what.data_source)

        # 判断是否为横截面数据
        is_cross_sectional = dataspec.shape in [DataShape.CS_1D, DataShape.CS_ND]

        # 检查数据源与数据形态的兼容性
        if is_cross_sectional and isinstance(adapter, FREDAdapter):
            raise DataFetchError(
                f"FRED数据源不支持横截面数据(shape={dataspec.shape})。"
                f"FRED仅提供时序数据,请使用CrossSectional或Synthetic数据源。"
            )

        if is_cross_sectional:
            # 横截面数据：传递 locale 和 entities
            locale = dataspec.language_config.locale if dataspec.language_config else 'zh-CN'
            entities = dataspec.where.entities if dataspec.where else None
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: adapter.fetch(dataspec.what.series_code, locale=locale, entities=entities)
            )
        else:
            # 时序数据
            start, end = self._compute_time_range(dataspec.when.range)

            # 如果适配器支持异步方法
            if hasattr(adapter, 'fetch_async'):
                df = await adapter.fetch_async(dataspec.what.series_code, start, end)
            else:
                # 回退到同步方法用executor
                loop = asyncio.get_event_loop()
                df = await loop.run_in_executor(
                    None,
                    adapter.fetch,
                    dataspec.what.series_code,
                    start,
                    end
                )

        # 应用变换（CPU操作，用executor）
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            self._apply_transforms,
            df,
            dataspec
        )

        return df

    async def fetch_and_build_payload_async(
        self,
        dataspec: DataSpec,
        question: Optional[str] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any], bool]:
        """异步获取数据并构建LLM Payload

        Args:
            dataspec: DataSpec
            question: 业务问题（模拟数据生成时使用）

        Returns:
            (DataFrame, llm_payload, is_synthetic)
        """
        # 获取数据
        df, is_synthetic = await self.fetch_async(dataspec, question)

        # 构建Payload（CPU操作）
        if dataspec.shape in [DataShape.TS_1D, DataShape.TS_ND]:
            llm_payload = self._build_ts_payload(df, dataspec)
        else:
            llm_payload = self._build_cs_payload(df, dataspec)
        
        # 如果是模拟数据，在 payload 中标记
        if is_synthetic:
            llm_payload["is_synthetic"] = True
            llm_payload["source"] = "LLM Generated Synthetic Data"

        return df, llm_payload, is_synthetic
