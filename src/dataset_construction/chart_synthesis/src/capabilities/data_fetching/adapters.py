"""数据源适配器"""
import logging
import asyncio
import requests
import httpx
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional, Dict, Any
from http.client import RemoteDisconnected
from urllib3.exceptions import ProtocolError
from requests.exceptions import ConnectionError as RequestsConnectionError
import pandas as pd

from ...utils.retry_decorator import retry_with_exceptions

logger = logging.getLogger(__name__)

# 网络重试相关异常
NETWORK_EXCEPTIONS = (
    ConnectionError,
    RemoteDisconnected,
    ProtocolError,
    RequestsConnectionError,
    TimeoutError,
)


class DataFetchError(Exception):
    """数据获取错误"""
    pass


class DataSourceAdapter(ABC):
    """数据源适配器基类"""

    @abstractmethod
    def fetch(
        self,
        series_code: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame:
        """获取数据"""
        pass


class FREDAdapter(DataSourceAdapter):
    """FRED数据适配器"""

    def fetch(
        self,
        series_code: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame:
        """从FRED获取数据

        Args:
            series_code: FRED序列代码，支持逗号分隔的多个代码
            start: 开始日期
            end: 结束日期

        Returns:
            DataFrame with 'date' index and 'value' column (单指标) 或多列 (多指标)
        """
        try:
            from pandas_datareader import data as pdr

            # 检查是否是多个指标（逗号分隔）
            if ',' in series_code:
                # 分割并清理指标列表
                codes = [code.strip() for code in series_code.split(',')]
                logger.info(f"从FRED获取多个指标: {codes}")

                # 分别获取每个指标
                dfs = []
                for code in codes:
                    try:
                        df_temp = pdr.DataReader(code, 'fred', start, end)
                        df_temp = df_temp.rename(columns={code: code})  # 保留原始代码名
                        dfs.append(df_temp)
                    except Exception as e:
                        logger.warning(f"获取指标 {code} 失败: {e}, 跳过")
                        continue

                if not dfs:
                    raise DataFetchError(f"所有指标获取失败: {codes}")

                # 合并所有指标（按日期索引）
                df = pd.concat(dfs, axis=1)
                df.index.name = 'date'

                # 统一处理: 始终确保有'value'列
                if len(df.columns) == 1:
                    # 单列: 重命名为'value'
                    df = df.rename(columns={df.columns[0]: 'value'})
                else:
                    # 多列: 取第一列作为主指标,重命名为'value',保留其他列
                    # 这确保DataFetcher始终能访问df['value']
                    first_col = df.columns[0]
                    df = df.rename(columns={first_col: 'value'})
                    logger.info(f"多指标数据: 使用 {first_col} 作为主指标'value',其他列保留")

                logger.info(f"FRED多指标数据获取成功: {len(df)}条数据点, {len(df.columns)}个指标")
                return df
            else:
                # 单个指标
                logger.info(f"从FRED获取数据: {series_code}")
                df = pdr.DataReader(series_code, 'fred', start, end)

                # 重命名列
                df = df.rename(columns={series_code: 'value'})
                df.index.name = 'date'

                logger.info(f"FRED数据获取成功: {len(df)}条数据点")
                return df

        except Exception as e:
            logger.error(f"FRED数据获取失败: {e}")
            raise

    async def fetch_async(
        self,
        series_code: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame:
        """异步从FRED获取数据(使用httpx)

        Args:
            series_code: FRED序列代码
            start: 开始日期
            end: 结束日期

        Returns:
            DataFrame
        """
        try:
            base_url = "https://fred.stlouisfed.org/graph/fredgraph.csv"

            # 检查是否是多个指标
            if ',' in series_code:
                codes = [code.strip() for code in series_code.split(',')]
                logger.info(f"异步从FRED获取多个指标: {codes}")

                async with httpx.AsyncClient(timeout=30) as client:
                    tasks = []
                    for code in codes:
                        params = {
                            'id': code,
                            'cosd': start.strftime('%Y-%m-%d'),
                            'coed': end.strftime('%Y-%m-%d')
                        }
                        tasks.append(client.get(base_url, params=params))

                    responses = await asyncio.gather(*tasks, return_exceptions=True)

                # 处理响应
                dfs = []
                for i, response in enumerate(responses):
                    if isinstance(response, Exception):
                        logger.warning(f"获取指标 {codes[i]} 失败: {response}")
                        continue

                    response.raise_for_status()
                    loop = asyncio.get_event_loop()
                    df_temp = await loop.run_in_executor(
                        None,
                        lambda text=response.text, code=codes[i]: pd.read_csv(
                            StringIO(text), parse_dates=['observation_date'], index_col='observation_date'
                        ).rename(columns={code: code})
                    )
                    dfs.append(df_temp)

                if not dfs:
                    raise DataFetchError(f"所有指标获取失败: {codes}")

                df = pd.concat(dfs, axis=1)
                df.index.name = 'date'

                if len(df.columns) == 1:
                    df = df.rename(columns={df.columns[0]: 'value'})
                else:
                    first_col = df.columns[0]
                    df = df.rename(columns={first_col: 'value'})

                logger.info(f"异步FRED多指标数据获取成功: {len(df)}条")
                return df
            else:
                # 单个指标
                logger.info(f"异步从FRED获取数据: {series_code}")

                async with httpx.AsyncClient(timeout=30) as client:
                    params = {
                        'id': series_code,
                        'cosd': start.strftime('%Y-%m-%d'),
                        'coed': end.strftime('%Y-%m-%d')
                    }
                    response = await client.get(base_url, params=params)
                    response.raise_for_status()

                # 解析CSV
                loop = asyncio.get_event_loop()
                df = await loop.run_in_executor(
                    None,
                    lambda: pd.read_csv(
                        StringIO(response.text),
                        parse_dates=['observation_date'],
                        index_col='observation_date'
                    )
                )

                df = df.rename(columns={series_code: 'value'})
                df.index.name = 'date'

                logger.info(f"异步FRED数据获取成功: {len(df)}条")
                return df

        except Exception as e:
            logger.error(f"异步FRED数据获取失败: {e}")
            raise DataFetchError(f"FRED异步获取失败: {e}")


class BaostockAdapter(DataSourceAdapter):
    """Baostock数据适配器 - A股指数数据
    
    特点：
    - 免费、无需注册、无限流
    - 支持 A股指数 日/周/月/分钟级别 K线数据
    - 返回 pandas DataFrame
    """
    
    def __init__(self):
        self._mapping = None
        self._logged_in = False
    
    def _load_mapping(self):
        """懒加载数据源映射配置"""
        if self._mapping is None:
            from pathlib import Path
            import yaml
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "data_source_mapping.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            self._mapping = config.get("baostock", {})
        return self._mapping
    
    def _ensure_login(self):
        """确保已登录 Baostock"""
        if not self._logged_in:
            import baostock as bs
            lg = bs.login()
            if lg.error_code != '0':
                logger.warning(f"Baostock登录失败: {lg.error_msg}")
            else:
                self._logged_in = True
                logger.info("Baostock登录成功")
    
    def fetch(
        self,
        series_code: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        locale: str = 'zh-CN',
        entities: Optional[list] = None
    ) -> pd.DataFrame:
        """从Baostock获取A股指数数据
        
        Args:
            series_code: 指标代码（如 index.sh000001.ohlcv）
            start: 开始日期
            end: 结束日期
            
        Returns:
            DataFrame with OHLCV data
        """
        import baostock as bs
        
        logger.info(f"从Baostock获取数据: {series_code}")
        
        # 确保登录
        self._ensure_login()
        
        # 加载映射
        mapping = self._load_mapping()
        
        # 获取 Baostock 代码
        if series_code in mapping:
            bs_code = mapping[series_code]
        else:
            bs_code = series_code
        
        # 设置日期范围
        start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        end_date = end.strftime('%Y-%m-%d') if end else datetime.now().strftime('%Y-%m-%d')
        
        # 查询数据
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"  # 不复权
        )
        
        if rs.error_code != '0':
            raise DataFetchError(f"Baostock数据获取失败: {rs.error_msg}")
        
        # 转换为 DataFrame
        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())
        
        if not data_list:
            raise DataFetchError(f"Baostock返回空数据: {series_code}")
        
        df = pd.DataFrame(data_list, columns=rs.fields)
        
        # 标准化列名和类型
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        # 转换数值列
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 添加 value 列（使用 close）
        df['value'] = df['close']
        
        logger.info(f"Baostock数据获取成功: {len(df)}条数据点")
        return df
    
    async def fetch_async(
        self,
        series_code: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        locale: str = 'zh-CN',
        entities: Optional[list] = None
    ) -> pd.DataFrame:
        """异步从Baostock获取数据（使用线程池执行同步方法）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.fetch(series_code, start, end, locale, entities)
        )


class YFinanceAdapter(DataSourceAdapter):
    """yfinance数据适配器 - 港股/全球指数/外汇
    
    特点：
    - 免费、无需注册
    - 支持港股（0700.HK）、全球指数（^HSI, ^GSPC）、外汇（USDCNY=X）
    - Yahoo Finance 限流宽松
    """
    
    def __init__(self):
        self._mapping = None
    
    def _load_mapping(self):
        """懒加载数据源映射配置"""
        if self._mapping is None:
            from pathlib import Path
            import yaml
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "data_source_mapping.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            self._mapping = config.get("yfinance", {})
        return self._mapping
    
    def _smart_fallback(self, series_code: str, mapping: dict) -> Optional[str]:
        """智能匹配指标代码，当精确匹配失败时尝试模糊匹配
        
        例如：commodity.metal.index.ohlcv → 匹配到 commodity.gold.ohlcv → GC=F
        """
        import random
        
        # 提取指标前缀
        parts = series_code.split('.')
        if len(parts) < 2:
            return None
        
        prefix = parts[0]  # 如 'commodity', 'index', 'fx'
        
        # 根据前缀选择默认指标（yfinance 支持的）
        fallback_map = {
            'commodity': ['commodity.gold.ohlcv', 'commodity.oil.wti.ohlcv', 'commodity.copper.ohlcv'],
            'index': ['index.global.spx.ohlcv', 'index.global.dji.ohlcv', 'index.global.ixic.ohlcv'],
            'fx': ['fx.eurusd.ohlcv', 'fx.gbpusd.ohlcv', 'fx.usdjpy.ohlcv'],
            'crypto': ['crypto.btc.ohlcv', 'crypto.eth.ohlcv'],
            # market.* 指标通常是 FRED 的，但如果错误地选了 yfinance，fallback 到指数
            'market': ['index.global.spx.ohlcv', 'index.global.dji.ohlcv', 'index.global.ixic.ohlcv'],
        }
        
        fallback_list = fallback_map.get(prefix, [])
        
        # 从候选列表中随机选择一个存在于映射表中的指标
        valid_fallbacks = [fb for fb in fallback_list if fb in mapping]
        if valid_fallbacks:
            chosen = random.choice(valid_fallbacks)
            logger.warning(f"指标 {series_code} 不存在，自动替换为 {chosen}")
            return mapping[chosen]
        
        return None
    
    def fetch(
        self,
        series_code: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        locale: str = 'zh-CN',
        entities: Optional[list] = None
    ) -> pd.DataFrame:
        """从yfinance获取数据
        
        Args:
            series_code: 指标代码（如 index.hsi.ohlcv）
            start: 开始日期
            end: 结束日期
            
        Returns:
            DataFrame with OHLCV data
        """
        import yfinance as yf
        
        logger.info(f"从yfinance获取数据: {series_code}")
        
        # 加载映射
        mapping = self._load_mapping()
        
        # 获取 yfinance 代码
        if series_code in mapping:
            yf_code = mapping[series_code]
        else:
            # 尝试智能匹配
            yf_code = self._smart_fallback(series_code, mapping)
            if yf_code is None:
                yf_code = series_code  # 最后尝试直接使用原代码
        
        # 设置日期范围
        start_date = start.strftime('%Y-%m-%d') if start else '2020-01-01'
        end_date = end.strftime('%Y-%m-%d') if end else datetime.now().strftime('%Y-%m-%d')
        
        # 下载数据
        df = yf.download(
            yf_code,
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=True
        )
        
        if df.empty:
            raise DataFetchError(f"yfinance返回空数据: {series_code} ({yf_code})")
        
        # 处理 MultiIndex 列名（yfinance 新版本返回 MultiIndex）
        if isinstance(df.columns, pd.MultiIndex):
            # 只取第一层列名
            df.columns = df.columns.get_level_values(0)
        
        # 标准化列名（yfinance 返回大写列名）
        df.columns = [str(col).lower() for col in df.columns]
        df.index.name = 'date'
        
        # 添加 value 列（使用 close）
        if 'close' in df.columns:
            df['value'] = df['close']
        
        logger.info(f"yfinance数据获取成功: {len(df)}条数据点")
        return df
    
    async def fetch_async(
        self,
        series_code: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        locale: str = 'zh-CN',
        entities: Optional[list] = None
    ) -> pd.DataFrame:
        """异步从yfinance获取数据（使用线程池执行同步方法）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.fetch(series_code, start, end, locale, entities)
        )


class EfinanceAdapter(DataSourceAdapter):
    """Efinance数据适配器 - 期货/ETF数据
    
    特点：
    - 免费、无需注册
    - 数据来源：东方财富
    - 支持期货、ETF、A股实时行情
    """
    
    def __init__(self):
        self._mapping = None
    
    def _load_mapping(self):
        """懒加载数据源映射配置"""
        if self._mapping is None:
            from pathlib import Path
            import yaml
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "data_source_mapping.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            self._mapping = config.get("efinance", {})
        return self._mapping
    
    def fetch(
        self,
        series_code: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        locale: str = 'zh-CN',
        entities: Optional[list] = None
    ) -> pd.DataFrame:
        """从Efinance获取数据
        
        Args:
            series_code: 指标代码（如 futures.au.ohlcv）
            start: 开始日期
            end: 结束日期
            
        Returns:
            DataFrame with OHLCV data
        """
        import efinance as ef
        
        logger.info(f"从Efinance获取数据: {series_code}")
        
        # 加载映射
        mapping = self._load_mapping()
        
        # 获取 Efinance 代码
        if series_code in mapping:
            ef_code = mapping[series_code]
        else:
            ef_code = series_code
        
        # 判断数据类型
        if series_code.startswith('futures.'):
            # 期货数据
            df = ef.futures.get_quote_history(ef_code)
        elif series_code.startswith('fund.etf.'):
            # ETF数据
            # Efinance ETF 代码格式: 510050
            df = ef.stock.get_quote_history(ef_code, klt=101)  # 101=日K
        else:
            # 默认使用期货接口
            df = ef.futures.get_quote_history(ef_code)
        
        if df is None or df.empty:
            raise DataFetchError(f"Efinance返回空数据: {series_code} ({ef_code})")
        
        # 标准化列名
        col_mapping = {
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '成交额': 'amount',
        }
        df = df.rename(columns=col_mapping)
        
        # 设置日期索引
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        
        # 筛选日期范围
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
        
        # 添加 value 列
        if 'close' in df.columns:
            df['value'] = df['close']
        
        logger.info(f"Efinance数据获取成功: {len(df)}条数据点")
        return df
    
    async def fetch_async(
        self,
        series_code: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        locale: str = 'zh-CN',
        entities: Optional[list] = None
    ) -> pd.DataFrame:
        """异步从Efinance获取数据（使用线程池执行同步方法）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.fetch(series_code, start, end, locale, entities)
        )


class CrossSectionalAdapter(DataSourceAdapter):
    """横截面数据适配器 - 支持国家统计局、IMF、世界银行、FAOSTAT"""

    # 支持的数据源配置
    SUPPORTED_SOURCES = {
        "china.stats.provinces.gdp": {
            "name": "省级GDP",
            "method": "_fetch_china_stats_gdp"
        },
        "china.stats.provinces.population": {
            "name": "省级人口",
            "method": "_fetch_china_stats_population"
        },
        "international.imf.inflation": {
            "name": "IMF通胀率",
            "method": "_fetch_imf_inflation"
        },
        "international.imf.gdp.growth": {
            "name": "IMF GDP增长率",
            "method": "_fetch_imf_gdp_growth"
        },
        "international.worldbank.gdp": {
            "name": "世界银行GDP",
            "method": "_fetch_worldbank_gdp"
        },
        "international.worldbank.population": {
            "name": "世界银行人口",
            "method": "_fetch_worldbank_population"
        },
        "international.fao.crop.production": {
            "name": "FAO农作物产量",
            "method": "_fetch_faostat_crop"
        }
    }

    def _get_api_lang(self, locale: str) -> str:
        """将 locale 转换为 API 语言参数"""
        if locale.startswith('en'):
            return 'en'
        elif locale.startswith('zh'):
            return 'zh'
        return 'en'  # 默认英文

    def fetch(
        self,
        series_code: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        locale: str = 'zh-CN',
        entities: Optional[list] = None
    ) -> pd.DataFrame:
        """从横截面数据源获取数据

        Args:
            series_code: 数据集标识符,如 "china.stats.provinces.gdp"
            start: 开始日期(横截面数据通常不需要)
            end: 结束日期(横截面数据通常不需要)
            locale: 语言代码,如 'en-US', 'zh-CN'
            entities: 实体列表,如 ['US', 'CN', 'DE'] 或省份代码

        Returns:
            DataFrame with 'entity' and 'value' columns
        """
        lang = self._get_api_lang(locale)

        if series_code not in self.SUPPORTED_SOURCES:
            # 兼容旧格式,使用前缀匹配
            if series_code.startswith("china.stats."):
                return self._fetch_china_stats_gdp(lang, entities)
            elif series_code.startswith("international.imf."):
                return self._fetch_imf_inflation(lang, entities)
            elif series_code.startswith("international.worldbank."):
                return self._fetch_worldbank_gdp(lang, entities)
            elif series_code.startswith("international.fao."):
                return self._fetch_faostat_crop(lang, entities)
            else:
                raise ValueError(
                    f"不支持的横截面数据源: {series_code}\n"
                    f"支持的数据源: {list(self.SUPPORTED_SOURCES.keys())}"
                )

        # 调用对应的获取方法
        config = self.SUPPORTED_SOURCES[series_code]
        method_name = config["method"]
        method = getattr(self, method_name)

        logger.info(f"获取横截面数据: {config['name']} (lang={lang}, entities={entities})")
        return method(lang, entities)

    # 中国省份名称映射（中->英）
    _CHINA_PROVINCE_NAMES = {
        '北京市': 'Beijing', '天津市': 'Tianjin', '河北省': 'Hebei',
        '山西省': 'Shanxi', '内蒙古自治区': 'Inner Mongolia',
        '辽宁省': 'Liaoning', '吉林省': 'Jilin', '黑龙江省': 'Heilongjiang',
        '上海市': 'Shanghai', '江苏省': 'Jiangsu', '浙江省': 'Zhejiang',
        '安徽省': 'Anhui', '福建省': 'Fujian', '江西省': 'Jiangxi',
        '山东省': 'Shandong', '河南省': 'Henan', '湖北省': 'Hubei',
        '湖南省': 'Hunan', '广东省': 'Guangdong', '广西壮族自治区': 'Guangxi',
        '海南省': 'Hainan', '重庆市': 'Chongqing', '四川省': 'Sichuan',
        '贵州省': 'Guizhou', '云南省': 'Yunnan', '西藏自治区': 'Tibet',
        '陕西省': 'Shaanxi', '甘肃省': 'Gansu', '青海省': 'Qinghai',
        '宁夏回族自治区': 'Ningxia', '新疆维吾尔自治区': 'Xinjiang',
    }

    def _fetch_china_stats_gdp(self, lang: str = 'zh', entities: Optional[list] = None) -> pd.DataFrame:
        """从国家统计局获取省级GDP数据 - 真实API，支持多语言和动态实体筛选"""
        try:
            url = "https://data.stats.gov.cn/easyquery.htm"

            params = {
                'm': 'QueryData',
                'dbcode': 'fsnd',  # 分省数据
                'rowcode': 'reg',  # 行:地区
                'colcode': 'sj',   # 列:时间
                'wds': '[]',
                'dfwds': '[{"wdcode":"zb","valuecode":"A0201"}]',  # 地区生产总值
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.post(url, data=params, headers=headers, timeout=30)
            data = response.json()

            # 构建实体筛选集（支持中英文省份名）
            target_entities = None
            if entities:
                target_entities = set(entities)
                # 添加中文名映射（如果传入的是英文）
                for zh, en in self._CHINA_PROVINCE_NAMES.items():
                    if en in target_entities:
                        target_entities.add(zh)

            provinces = []
            if 'returndata' in data and 'datanodes' in data['returndata']:
                wdnodes = data['returndata'].get('wdnodes', [])
                region_map = {}
                for node in wdnodes:
                    if node['wdcode'] == 'reg':
                        for item in node.get('nodes', []):
                            region_map[item['code']] = item['cname']

                for node in data['returndata']['datanodes']:
                    wds = node.get('wds', [])
                    reg_code = None
                    for wd in wds:
                        if wd['wdcode'] == 'reg':
                            reg_code = wd['valuecode']
                            break

                    if reg_code and reg_code in region_map:
                        entity_name_zh = region_map[reg_code]
                        # 根据 entities 筛选
                        if target_entities and entity_name_zh not in target_entities:
                            continue
                        # 英文时翻译省份名称
                        entity_name = self._CHINA_PROVINCE_NAMES.get(entity_name_zh, entity_name_zh) if lang == 'en' else entity_name_zh
                        provinces.append({
                            'entity': entity_name,
                            'value': float(node['data'].get('data', 0))
                        })

            df = pd.DataFrame(provinces)
            logger.info(f"国家统计局GDP数据获取成功: {len(df)}条记录 (lang={lang}, entities={entities})")
            return df

        except Exception as e:
            logger.error(f"国家统计局GDP数据获取失败: {e}")
            raise DataFetchError(f"国家统计局API调用失败: {e}")

    def _fetch_china_stats_population(self, lang: str = 'zh', entities: Optional[list] = None) -> pd.DataFrame:
        """从国家统计局获取省级人口数据 - 真实API，支持多语言和动态实体筛选"""
        try:
            url = "https://data.stats.gov.cn/easyquery.htm"

            params = {
                'm': 'QueryData',
                'dbcode': 'fsnd',
                'rowcode': 'reg',
                'colcode': 'sj',
                'wds': '[]',
                'dfwds': '[{"wdcode":"zb","valuecode":"A0301"}]',  # 人口数(年末常住人口)
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.post(url, data=params, headers=headers, timeout=30)
            data = response.json()

            # 构建实体筛选集（支持中英文省份名）
            target_entities = None
            if entities:
                target_entities = set(entities)
                for zh, en in self._CHINA_PROVINCE_NAMES.items():
                    if en in target_entities:
                        target_entities.add(zh)

            provinces = []
            if 'returndata' in data and 'datanodes' in data['returndata']:
                wdnodes = data['returndata'].get('wdnodes', [])
                region_map = {}
                for node in wdnodes:
                    if node['wdcode'] == 'reg':
                        for item in node.get('nodes', []):
                            region_map[item['code']] = item['cname']

                for node in data['returndata']['datanodes']:
                    wds = node.get('wds', [])
                    reg_code = None
                    for wd in wds:
                        if wd['wdcode'] == 'reg':
                            reg_code = wd['valuecode']
                            break

                    if reg_code and reg_code in region_map:
                        entity_name_zh = region_map[reg_code]
                        # 根据 entities 筛选
                        if target_entities and entity_name_zh not in target_entities:
                            continue
                        # 英文时翻译省份名称
                        entity_name = self._CHINA_PROVINCE_NAMES.get(entity_name_zh, entity_name_zh) if lang == 'en' else entity_name_zh
                        provinces.append({
                            'entity': entity_name,
                            'value': float(node['data'].get('data', 0))
                        })

            df = pd.DataFrame(provinces)
            logger.info(f"国家统计局人口数据获取成功: {len(df)}条记录 (lang={lang}, entities={entities})")
            return df

        except Exception as e:
            logger.error(f"国家统计局人口数据获取失败: {e}")
            raise DataFetchError(f"国家统计局API调用失败: {e}")

    # IMF 国家代码到名称映射（多语言）
    _IMF_COUNTRY_NAMES = {
        'en': {
            'CHN': 'China', 'USA': 'United States', 'JPN': 'Japan',
            'GBR': 'United Kingdom', 'DEU': 'Germany', 'IND': 'India',
            'FRA': 'France', 'ITA': 'Italy', 'BRA': 'Brazil', 'CAN': 'Canada'
        },
        'zh': {
            'CHN': '中国', 'USA': '美国', 'JPN': '日本',
            'GBR': '英国', 'DEU': '德国', 'IND': '印度',
            'FRA': '法国', 'ITA': '意大利', 'BRA': '巴西', 'CAN': '加拿大'
        }
    }

    def _fetch_imf_inflation(self, lang: str = 'zh', entities: Optional[list] = None) -> pd.DataFrame:
        """从IMF获取通胀率数据 - 真实API，支持多语言和动态实体"""
        try:
            url = "https://www.imf.org/external/datamapper/api/v1/PCPIPCH"
            response = requests.get(url, timeout=30)

            if response.status_code != 200:
                raise DataFetchError(f"IMF API请求失败: HTTP {response.status_code}")

            data = response.json()

            # 根据语言选择名称映射
            countries_map = self._IMF_COUNTRY_NAMES.get(lang, self._IMF_COUNTRY_NAMES['en'])

            # 确定要筛选的国家代码 (ISO 3166-1 alpha-3)
            target_codes = set(entities) if entities else set(countries_map.keys())

            inflation_data = []
            if 'values' in data and 'PCPIPCH' in data['values']:
                for country_code, years_data in data['values']['PCPIPCH'].items():
                    if country_code in target_codes and years_data:
                        latest_year = max(years_data.keys())
                        # 获取国家名，优先从映射获取，否则用代码
                        entity_name = countries_map.get(country_code, country_code)
                        inflation_data.append({
                            'entity': entity_name,
                            'value': float(years_data[latest_year])
                        })

            if not inflation_data:
                raise DataFetchError("IMF API返回数据为空")

            df = pd.DataFrame(inflation_data)
            logger.info(f"IMF通胀数据获取成功: {len(df)}条记录 (lang={lang}, entities={list(target_codes)})")
            return df

        except Exception as e:
            logger.error(f"IMF通胀数据获取失败: {e}")
            raise DataFetchError(f"IMF API调用失败: {e}")

    def _fetch_imf_gdp_growth(self, lang: str = 'zh', entities: Optional[list] = None) -> pd.DataFrame:
        """从IMF获取GDP增长率数据 - 真实API，支持多语言和动态实体"""
        try:
            url = "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH"
            response = requests.get(url, timeout=30)

            if response.status_code != 200:
                raise DataFetchError(f"IMF API请求失败: HTTP {response.status_code}")

            data = response.json()

            # 根据语言选择名称映射
            countries_map = self._IMF_COUNTRY_NAMES.get(lang, self._IMF_COUNTRY_NAMES['en'])

            # 确定要筛选的国家代码 (ISO 3166-1 alpha-3)
            target_codes = set(entities) if entities else set(countries_map.keys())

            growth_data = []
            if 'values' in data and 'NGDP_RPCH' in data['values']:
                for country_code, years_data in data['values']['NGDP_RPCH'].items():
                    if country_code in target_codes and years_data:
                        latest_year = max(years_data.keys())
                        # 获取国家名，优先从映射获取，否则用代码
                        entity_name = countries_map.get(country_code, country_code)
                        growth_data.append({
                            'entity': entity_name,
                            'value': float(years_data[latest_year])
                        })

            if not growth_data:
                raise DataFetchError("IMF API返回数据为空")

            df = pd.DataFrame(growth_data)
            logger.info(f"IMF GDP增长数据获取成功: {len(df)}条记录 (lang={lang}, entities={list(target_codes)})")
            return df

        except Exception as e:
            logger.error(f"IMF GDP增长数据获取失败: {e}")
            raise DataFetchError(f"IMF API调用失败: {e}")

    def _fetch_worldbank_gdp(self, lang: str = 'zh', entities: Optional[list] = None) -> pd.DataFrame:
        """从世界银行获取GDP数据 - 真实API，支持多语言和动态实体"""
        try:
            # 使用传入的 entities (ISO 3166-1 alpha-3)，否则使用默认值
            countries = entities if entities else ['CHN', 'USA', 'JPN', 'DEU', 'IND']

            indicator_code = 'NY.GDP.MKTP.CD'  # GDP总量(现价美元)
            # World Bank API 支持 language 参数: en, zh, es, fr, ar
            api_lang = 'zh' if lang == 'zh' else 'en'
            url = f"https://api.worldbank.org/v2/{api_lang}/country/{';'.join(countries)}/indicator/{indicator_code}?date=2022&format=json&per_page=100"

            response = requests.get(url, timeout=30)

            if response.status_code != 200:
                raise DataFetchError(f"世界银行API请求失败: HTTP {response.status_code}")

            data = response.json()

            gdp_data = []
            if len(data) > 1 and data[1]:
                for item in data[1]:
                    if item['value']:
                        # API 直接返回对应语言的国家名
                        gdp_data.append({
                            'entity': item['country']['value'],
                            'value': float(item['value']) / 1e12  # 转换为万亿美元
                        })

            if not gdp_data:
                raise DataFetchError("世界银行API返回数据为空")

            df = pd.DataFrame(gdp_data)
            logger.info(f"世界银行GDP数据获取成功: {len(df)}条记录 (lang={lang}, entities={countries})")
            return df

        except Exception as e:
            logger.error(f"世界银行GDP数据获取失败: {e}")
            raise DataFetchError(f"世界银行API调用失败: {e}")

    def _fetch_worldbank_population(self, lang: str = 'zh', entities: Optional[list] = None) -> pd.DataFrame:
        """从世界银行获取人口数据 - 真实API，支持多语言和动态实体"""
        try:
            # 使用传入的 entities (ISO 3166-1 alpha-3)，否则使用默认值
            countries = entities if entities else ['CHN', 'IND', 'USA', 'IDN', 'PAK']

            indicator_code = 'SP.POP.TOTL'  # 总人口
            api_lang = 'zh' if lang == 'zh' else 'en'
            url = f"https://api.worldbank.org/v2/{api_lang}/country/{';'.join(countries)}/indicator/{indicator_code}?date=2022&format=json&per_page=100"

            response = requests.get(url, timeout=30)

            if response.status_code != 200:
                raise DataFetchError(f"世界银行API请求失败: HTTP {response.status_code}")

            data = response.json()

            pop_data = []
            if len(data) > 1 and data[1]:
                for item in data[1]:
                    if item['value']:
                        # API 直接返回对应语言的国家名
                        pop_data.append({
                            'entity': item['country']['value'],
                            'value': float(item['value']) / 1e8  # 转换为亿人
                        })

            if not pop_data:
                raise DataFetchError("世界银行API返回数据为空")

            df = pd.DataFrame(pop_data)
            logger.info(f"世界银行人口数据获取成功: {len(df)}条记录 (lang={lang}, entities={countries})")
            return df

        except Exception as e:
            logger.error(f"世界银行人口数据获取失败: {e}")
            raise DataFetchError(f"世界银行API调用失败: {e}")

    # FAOSTAT 农作物名称映射（英->中）
    _FAOSTAT_CROP_NAMES = {
        'Wheat': '小麦', 'Rice': '大米', 'Rice, paddy': '稻谷',
        'Maize': '玉米', 'Soybeans': '大豆', 'Potatoes': '马铃薯',
        'Sugar cane': '甘蔗', 'Tomatoes': '番茄', 'Apples': '苹果',
    }

    def _fetch_faostat_crop(self, lang: str = 'zh', entities: Optional[list] = None) -> pd.DataFrame:
        """从FAOSTAT获取农作物产量数据 - 真实API，支持多语言和动态实体筛选"""
        try:
            # FAOSTAT API 默认返回英文
            url = "https://fenixservices.fao.org/faostat/api/v1/en/data/QCL"

            params = {
                'area': '351',       # 中国区域代码
                'element': '5510',   # 产量元素
                'item': '15,27,56,71,83',  # 小麦,大米,玉米,大豆,马铃薯
                'year': '2021'
            }

            response = requests.get(url, params=params, timeout=30)

            if response.status_code != 200:
                raise DataFetchError(f"FAOSTAT API请求失败: HTTP {response.status_code}")

            data = response.json()

            if 'data' not in data or len(data['data']) == 0:
                raise DataFetchError("FAOSTAT API返回数据为空")

            # 构建实体筛选集（支持中英文作物名）
            target_entities = None
            if entities:
                target_entities = set(entities)
                # 添加英文名映射（如果传入的是中文）
                for en, zh in self._FAOSTAT_CROP_NAMES.items():
                    if zh in target_entities:
                        target_entities.add(en)

            crop_data = []
            for item in data['data']:
                entity_name_en = item.get('Item', 'N/A')
                # 根据 entities 筛选
                if target_entities and entity_name_en not in target_entities:
                    continue
                # 中文时翻译作物名称
                entity_name = self._FAOSTAT_CROP_NAMES.get(entity_name_en, entity_name_en) if lang == 'zh' else entity_name_en
                crop_data.append({
                    'entity': entity_name,
                    'value': float(item.get('Value', 0))
                })

            df = pd.DataFrame(crop_data)
            logger.info(f"FAOSTAT农作物数据获取成功: {len(df)}条记录 (lang={lang}, entities={entities})")
            return df

        except Exception as e:
            logger.error(f"FAOSTAT数据获取失败: {e}")
            raise DataFetchError(f"FAOSTAT API调用失败: {e}")
