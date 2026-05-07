"""模拟数据生成器 - 使用 LLM 生成符合真实世界特征的模拟数据"""
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
import pandas as pd
import yaml
from openai import OpenAI, AsyncOpenAI
from json_repair import repair_json

from ...models.dataspec import DataSpec, DataShape
from ...utils.config_loader import load_llm_config

logger = logging.getLogger(__name__)


class SyntheticDataError(Exception):
    """模拟数据生成错误"""
    pass


class SyntheticDataGenerator:
    """模拟数据生成器 - 调用 LLM 生成模拟数据"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化
        
        Args:
            config: LLM配置，如果为None则从配置文件加载
        """
        if config is None:
            config = load_llm_config()
        
        self.config = config
        # 使用 planner 的配置（模拟数据生成与规划类似）
        self.generator_config = config["pipeline_models"]["planner"]
        self.provider_config = config["providers"][self.generator_config["provider"]]
        
        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            api_key=self.provider_config["api_key"],
            base_url=self.provider_config["base_url"]
        )
        self.async_client = AsyncOpenAI(
            api_key=self.provider_config["api_key"],
            base_url=self.provider_config["base_url"]
        )
        
        # 加载触发条件配置
        config_dir = Path(__file__).parent.parent.parent.parent / "config"
        with open(config_dir / "synthetic_triggers.yaml", "r", encoding="utf-8") as f:
            self.triggers_config = yaml.safe_load(f)
        
        # 加载 Prompt 模板
        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
        with open(prompts_dir / "synthetic_data_template.md", "r", encoding="utf-8") as f:
            self.prompt_template = f.read().strip()
    
    def should_use_synthetic(self, dataspec: DataSpec) -> bool:
        """判断是否应该使用模拟数据
        
        Args:
            dataspec: DataSpec
            
        Returns:
            True 表示应该使用模拟数据
        """
        import random
        
        triggers = self.triggers_config.get("triggers", {})
        
        # 检查数据形态触发
        shape_trigger = triggers.get("by_shape", {})
        if shape_trigger.get("enabled", False):
            if dataspec.shape in shape_trigger.get("shapes", []):
                probability = shape_trigger.get("probability", 1.0)
                if random.random() < probability:
                    logger.info(f"触发模拟数据: 数据形态 {dataspec.shape} (概率 {probability})")
                    return True
                else:
                    logger.info(f"跳过模拟数据: 数据形态 {dataspec.shape} 未命中概率 {probability}")
        
        # 检查主题触发
        theme_trigger = triggers.get("by_theme", {})
        if theme_trigger.get("enabled", False):
            # 从 dataspec 获取主题
            theme = getattr(dataspec, 'theme', None)
            if theme and theme in theme_trigger.get("themes", []):
                probability = theme_trigger.get("probability", 1.0)
                if random.random() < probability:
                    logger.info(f"触发模拟数据: 主题 {theme} (概率 {probability})")
                    return True
                else:
                    logger.info(f"跳过模拟数据: 主题 {theme} 未命中概率 {probability}")
        
        # 检查图表类型触发
        chart_trigger = triggers.get("by_chart_type", {})
        if chart_trigger.get("enabled", False):
            if dataspec.chart_type in chart_trigger.get("chart_types", []):
                probability = chart_trigger.get("probability", 1.0)
                if random.random() < probability:
                    logger.info(f"触发模拟数据: 图表类型 {dataspec.chart_type} (概率 {probability})")
                    return True
                else:
                    logger.info(f"跳过模拟数据: 图表类型 {dataspec.chart_type} 未命中概率 {probability}")
        
        return False
    
    def generate(
        self,
        dataspec: DataSpec,
        question: str,
        error_context: Optional[str] = None
    ) -> pd.DataFrame:
        """生成模拟数据
        
        Args:
            dataspec: DataSpec
            question: 业务问题
            error_context: 错误上下文（重试时使用）
            
        Returns:
            DataFrame
        """
        logger.info(f"开始生成模拟数据: {dataspec.chart_type}/{dataspec.shape}")
        
        # 构建 Prompt
        prompt = self._build_prompt(dataspec, question, error_context)
        
        # 调用 LLM
        try:
            response = self.client.chat.completions.create(
                model=self.generator_config["model"],
                messages=[
                    {"role": "system", "content": "你是一位金融数据专家，擅长生成符合真实世界特征的模拟数据。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,  # 稍高的温度以增加多样性
                max_tokens=self.generator_config["max_tokens"]
            )
            
            content = response.choices[0].message.content.strip()
            
            # 解析 JSON
            df = self._parse_response(content, dataspec)
            
            logger.info(f"模拟数据生成成功: {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"模拟数据生成失败: {e}")
            raise SyntheticDataError(f"模拟数据生成失败: {e}")
    
    async def generate_async(
        self,
        dataspec: DataSpec,
        question: str,
        error_context: Optional[str] = None
    ) -> pd.DataFrame:
        """异步生成模拟数据
        
        Args:
            dataspec: DataSpec
            question: 业务问题
            error_context: 错误上下文（重试时使用）
            
        Returns:
            DataFrame
        """
        logger.info(f"开始异步生成模拟数据: {dataspec.chart_type}/{dataspec.shape}")
        
        # 构建 Prompt
        prompt = self._build_prompt(dataspec, question, error_context)
        
        # 异步调用 LLM
        try:
            response = await self.async_client.chat.completions.create(
                model=self.generator_config["model"],
                messages=[
                    {"role": "system", "content": "你是一位金融数据专家，擅长生成符合真实世界特征的模拟数据。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=self.generator_config["max_tokens"]
            )
            
            content = response.choices[0].message.content.strip()
            
            # 解析 JSON
            df = self._parse_response(content, dataspec)
            
            logger.info(f"异步模拟数据生成成功: {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"异步模拟数据生成失败: {e}")
            raise SyntheticDataError(f"模拟数据生成失败: {e}")
    
    def _build_prompt(
        self,
        dataspec: DataSpec,
        question: str,
        error_context: Optional[str] = None
    ) -> str:
        """构建 Prompt
        
        Args:
            dataspec: DataSpec
            question: 业务问题
            error_context: 错误上下文
            
        Returns:
            Prompt 字符串
        """
        # 获取默认配置
        gen_config = self.triggers_config.get("generation", {})
        default_entity_count = gen_config.get("default_entity_count", {})
        default_variable_count = gen_config.get("default_variable_count", {})
        
        # 确定实体数量
        entity_count = len(dataspec.where.entities) if dataspec.where.entities else \
                       default_entity_count.get(dataspec.shape, 10)
        
        # 确定变量数量
        variable_count = default_variable_count.get(dataspec.shape, 
                         default_variable_count.get(dataspec.chart_type, 3))
        
        # 获取实体列表
        entities = dataspec.where.entities if dataspec.where.entities else "（请根据主题自行选择合适的实体）"
        
        # 获取语言
        language = dataspec.language_config.locale if dataspec.language_config else "zh-CN"
        
        # 获取主题
        theme = getattr(dataspec, 'theme', dataspec.what.indicator_id.split('.')[0] if dataspec.what else "general")
        
        # 填充模板
        prompt = self.prompt_template.format(
            question=question,
            shape=dataspec.shape,
            chart_type=dataspec.chart_type,
            theme=theme,
            language=language,
            entity_type=dataspec.where.entity_type if dataspec.where else "country",
            entity_count=entity_count,
            entities=entities,
            variable_count=variable_count,
            variable_names="（请根据问题自行设计变量名）"
        )
        
        if error_context:
            prompt += f"\n\n**上次错误**: {error_context}\n请修正后重新生成。"
        
        return prompt
    
    def _parse_response(self, content: str, dataspec: DataSpec) -> pd.DataFrame:
        """解析 LLM 响应
        
        Args:
            content: LLM 响应内容
            dataspec: DataSpec
            
        Returns:
            DataFrame
        """
        # 移除可能的 markdown 标记
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # 解析 JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败，尝试修复: {e}")
            try:
                repaired = repair_json(content, return_objects=False)
                result = json.loads(repaired)
                logger.info("JSON 修复成功")
            except Exception as repair_error:
                logger.error(f"JSON 修复失败: {repair_error}")
                raise SyntheticDataError(f"无法解析模拟数据: {e}")
        
        # 提取数据
        if isinstance(result, dict) and "data" in result:
            data = result["data"]
        elif isinstance(result, list):
            data = result
        else:
            raise SyntheticDataError(f"无效的数据格式: {type(result)}")
        
        # 转换为 DataFrame
        df = pd.DataFrame(data)
        
        # 根据数据形态处理索引和列
        if dataspec.shape in [DataShape.TS_1D, DataShape.TS_ND]:
            # 时间序列数据：设置日期索引
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
                df = df.sort_index()
            # 确保有 value 列
            if 'value' not in df.columns:
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    df['value'] = df[numeric_cols[0]]
        else:
            # 横截面数据：设置实体索引
            if 'entity' in df.columns:
                df = df.set_index('entity')
            # 确保有 value 列（如果是单变量）
            if dataspec.shape == DataShape.CS_1D and 'value' not in df.columns:
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    df['value'] = df[numeric_cols[0]]
        
        return df
    
    def generate_with_retry(
        self,
        dataspec: DataSpec,
        question: str,
        max_retries: int = 3
    ) -> pd.DataFrame:
        """带重试的生成
        
        Args:
            dataspec: DataSpec
            question: 业务问题
            max_retries: 最大重试次数
            
        Returns:
            DataFrame
        """
        error_context = None
        
        for attempt in range(max_retries):
            try:
                return self.generate(dataspec, question, error_context)
            except SyntheticDataError as e:
                error_context = str(e)
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"模拟数据生成失败 (尝试 {attempt + 1}/{max_retries}): {e}")
        
        raise SyntheticDataError("不应该到达这里")
    
    async def generate_with_retry_async(
        self,
        dataspec: DataSpec,
        question: str,
        max_retries: int = 3
    ) -> pd.DataFrame:
        """异步带重试的生成
        
        Args:
            dataspec: DataSpec
            question: 业务问题
            max_retries: 最大重试次数
            
        Returns:
            DataFrame
        """
        error_context = None
        
        for attempt in range(max_retries):
            try:
                return await self.generate_async(dataspec, question, error_context)
            except SyntheticDataError as e:
                error_context = str(e)
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"异步模拟数据生成失败 (尝试 {attempt + 1}/{max_retries}): {e}")
        
        raise SyntheticDataError("不应该到达这里")

