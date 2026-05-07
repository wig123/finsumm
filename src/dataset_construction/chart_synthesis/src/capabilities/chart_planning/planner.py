"""Chart Planner - 业务规划层"""
import json
import logging
import asyncio
import random
from typing import Dict, Any, Optional
from pathlib import Path
import yaml
from openai import OpenAI, AsyncOpenAI
from json_repair import repair_json

from ...models.planner_models import PlannerInput, PlannerOutput
from ...utils.config_loader import load_llm_config
from ...utils.retry_decorator import retry_on_failure

logger = logging.getLogger(__name__)


class PlannerError(Exception):
    """Planner错误"""
    pass


class ChartPlanner:
    """图表规划器 - 调用Planner LLM生成业务逻辑"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化

        Args:
            config: LLM配置,如果为None则从配置文件加载
        """
        if config is None:
            config = load_llm_config()

        self.config = config
        self.planner_config = config["pipeline_models"]["planner"]
        self.provider_config = config["providers"][self.planner_config["provider"]]

        # 初始化OpenAI客户端（同步和异步）
        self.client = OpenAI(
            api_key=self.provider_config["api_key"],
            base_url=self.provider_config["base_url"]
        )
        self.async_client = AsyncOpenAI(
            api_key=self.provider_config["api_key"],
            base_url=self.provider_config["base_url"]
        )

        # 加载 theme 映射配置
        config_dir = Path(__file__).parent.parent.parent.parent / "config"
        with open(config_dir / "theme_mapping.yaml", "r", encoding="utf-8") as f:
            self.theme_mapping = yaml.safe_load(f)["themes"]

        # 加载数据源映射配置
        with open(config_dir / "data_source_mapping.yaml", "r", encoding="utf-8") as f:
            self.data_source_mapping = yaml.safe_load(f)

        # 加载图表类型映射配置（包含数据形态约束）
        with open(config_dir / "chart_library_mapping.yaml", "r", encoding="utf-8") as f:
            self.chart_mapping = yaml.safe_load(f).get("chart_types", {})

        # 加载提示词模板
        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
        with open(prompts_dir / "planner_system.txt", "r", encoding="utf-8") as f:
            self.system_prompt = f.read().strip()
        with open(prompts_dir / "planner_user_template.md", "r", encoding="utf-8") as f:
            self.user_prompt_template = f.read().strip()

    def build_prompt(
        self,
        planner_input: PlannerInput,
        error_context: Optional[str] = None
    ) -> str:
        """构建Planner Prompt

        Args:
            planner_input: Planner输入
            error_context: 错误上下文(重试时使用)

        Returns:
            Prompt字符串
        """
        # 获取 theme 配置
        theme_config = self.theme_mapping[planner_input.theme]

        # 构建主题描述
        theme_label = theme_config["label"] if planner_input.language == "zh-CN" else theme_config["label_en"]

        # 生成动态指标列表（按主题过滤）
        indicators_text = self._generate_indicators_text(theme=planner_input.theme)

        # 生成图表类型约束文本
        chart_constraints_text = self._generate_chart_constraints_text(planner_input.chart_type)

        # ⭐ 随机选择一个推荐指标（提升多样性）
        import random
        preferred = theme_config.get('preferred_indicators', [])
        if preferred:
            suggested_indicator = random.choice(preferred)
            if planner_input.language == "zh-CN":
                indicator_hint = f"\n💡 **建议指标**: {suggested_indicator}（从 {len(preferred)} 个候选中随机选择，优先使用此指标以提升多样性）"
            else:
                indicator_hint = f"\n💡 **Suggested Indicator**: {suggested_indicator} (randomly selected from {len(preferred)} candidates, prioritize this for diversity)"
        else:
            indicator_hint = ""

        # 使用模板填充变量
        prompt = self.user_prompt_template.format(
            chart_type=planner_input.chart_type,
            language=planner_input.language,
            theme=planner_input.theme,
            theme_label=theme_label,
            theme_description=theme_config['description'],
            theme_iptc=theme_config.get('iptc', []),
            preferred_indicators=theme_config.get('preferred_indicators', []),
            typical_data_sources=theme_config.get('typical_data_sources', []),
            available_indicators=indicators_text,
            chart_type_constraints=chart_constraints_text,
            indicator_hint=indicator_hint
        )

        if error_context:
            prompt += f"\n\n**上次错误**: {error_context}\n请修正后重新输出JSON。"

        return prompt

    def _generate_indicators_text(self, theme: str = None) -> str:
        """从data_source_mapping生成指标列表文本
        
        Args:
            theme: 主题名称，如果提供则只返回与主题相关的指标
        
        Returns:
            指标列表文本
        """
        # 获取主题的指标前缀过滤列表
        indicator_prefixes = []
        if theme and theme in self.theme_mapping:
            indicator_prefixes = self.theme_mapping[theme].get("indicator_prefixes", [])
        
        def matches_prefix(indicator: str) -> bool:
            """检查指标是否匹配任一前缀"""
            if not indicator_prefixes:
                return True  # 无过滤条件时返回全部
            return any(indicator.startswith(prefix) for prefix in indicator_prefixes)
        
        lines = []

        # FRED指标
        fred_mapping = self.data_source_mapping.get("fred", {})
        fred_indicators = [(ind, code) for ind, code in fred_mapping.items() if matches_prefix(ind)]
        if fred_indicators:
            lines.append("### FRED数据源(时序数据)")
            for indicator, series_code in fred_indicators:
                lines.append(f"- {indicator} → {series_code}")

        # AKShare 数据源已移除（原因：性能瓶颈、不需要其独有数据）
        # 替代方案：FRED + yfinance + baostock + efinance + LLM 合成

        # yfinance指标（OHLC数据）
        yfinance_mapping = self.data_source_mapping.get("yfinance", {})
        yfinance_indicators = [(ind, code) for ind, code in yfinance_mapping.items() if matches_prefix(ind)]
        if yfinance_indicators:
            lines.append("\n### yfinance数据源(全球指数/期货/外汇OHLC数据)")
            for indicator, series_code in yfinance_indicators:
                lines.append(f"- {indicator} → {series_code}")

        # Efinance指标（中国期货/ETF OHLC数据）
        efinance_mapping = self.data_source_mapping.get("efinance", {})
        efinance_indicators = [(ind, code) for ind, code in efinance_mapping.items() if matches_prefix(ind)]
        if efinance_indicators:
            lines.append("\n### Efinance数据源(中国期货/ETF OHLC数据)")
            for indicator, series_code in efinance_indicators:
                lines.append(f"- {indicator} → {series_code}")

        # Baostock指标（A股指数OHLC数据）
        baostock_mapping = self.data_source_mapping.get("baostock", {})
        baostock_indicators = [(ind, code) for ind, code in baostock_mapping.items() if matches_prefix(ind)]
        if baostock_indicators:
            lines.append("\n### Baostock数据源(A股指数OHLC数据)")
            for indicator, series_code in baostock_indicators:
                lines.append(f"- {indicator} → {series_code}")

        # 横截面数据
        cs_mapping = self.data_source_mapping.get("cross_sectional", {})
        cs_indicators = [(ind, cfg) for ind, cfg in cs_mapping.items() if matches_prefix(ind)]
        if cs_indicators:
            lines.append("\n### 横截面数据源")
            for indicator, config in cs_indicators:
                if isinstance(config, dict):
                    source = config.get("source", "")
                    desc = config.get("description", "")
                    lines.append(f"- {indicator} (来源:{source}, {desc})")
                else:
                    lines.append(f"- {indicator}")

        return "\n".join(lines)

    def _generate_chart_constraints_text(self, chart_type: str) -> str:
        """根据图表类型生成数据约束文本

        Args:
            chart_type: 图表类型

        Returns:
            约束文本，如果没有约束则返回空字符串
        """
        chart_config = self.chart_mapping.get(chart_type, {})
        lines = []

        # 获取必需的数据形态
        required_shapes = chart_config.get("required_shapes", [])
        if required_shapes:
            shapes_str = ", ".join(required_shapes)
            lines.append(f"- **允许的数据形态**: {shapes_str}")

        # 获取数据约束
        data_constraints = chart_config.get("data_constraints", [])
        for constraint in data_constraints:
            lines.append(f"- {constraint}")

        if lines:
            return "## 当前图表类型数据约束 (CRITICAL)\n" + "\n".join(lines)
        return ""

    @retry_on_failure(max_retries=3, exceptions=(json.JSONDecodeError, PlannerError))
    def plan(
        self,
        planner_input: PlannerInput,
        error_context: Optional[str] = None
    ) -> tuple[PlannerOutput, Dict[str, Any]]:
        """执行规划

        Args:
            planner_input: Planner输入
            error_context: 错误上下文(重试时使用)

        Returns:
            (PlannerOutput, llm_trace) - llm_trace包含完整的prompt和response

        Raises:
            PlannerError: 规划失败
        """
        logger.info(f"开始规划: {planner_input.chart_type} / {planner_input.language}")

        # 构建Prompt
        prompt = self.build_prompt(planner_input, error_context)

        # 构建完整的messages
        messages = [
            {
                "role": "system",
                "content": self.system_prompt
            },
            {"role": "user", "content": prompt}
        ]

        # 调用LLM
        try:
            response = self.client.chat.completions.create(
                model=self.planner_config["model"],
                messages=messages,
                temperature=self.planner_config["temperature"],
                max_tokens=self.planner_config["max_tokens"]
            )

            content = response.choices[0].message.content

            # 检查content是否为空
            if not content or content.strip() == "":
                logger.error(f"LLM返回空响应\nAPI response: {response}")
                logger.error(f"Response model: {response.model}")
                logger.error(f"Response finish_reason: {response.choices[0].finish_reason}")
                raise PlannerError("LLM返回空响应,可能是API限流或内容审查")

            content = content.strip()

            # 移除可能的markdown标记
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 解析JSON - 先尝试repair_json修复不完整的JSON
            try:
                output_dict = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失败,尝试使用json_repair修复: {e}")
                try:
                    # 使用json_repair修复不完整的JSON
                    repaired_content = repair_json(content, return_objects=False)
                    output_dict = json.loads(repaired_content)
                    logger.info("JSON修复成功")
                except Exception as repair_error:
                    logger.error(f"JSON修复失败: {repair_error}\n原始内容: {content[:800]}")
                    raise PlannerError(f"JSON解析失败: {e}")

            # 验证并构建PlannerOutput
            try:
                planner_output = PlannerOutput(**output_dict)
            except Exception as e:
                logger.error(f"PlannerOutput验证失败: {e}\n数据: {output_dict}")
                raise PlannerError(f"输出验证失败: {e}")

            # 构建LLM trace记录
            llm_trace = {
                "model": self.planner_config["model"],
                "temperature": self.planner_config["temperature"],
                "max_tokens": self.planner_config["max_tokens"],
                "messages": messages,
                "response": {
                    "content": content,
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                        "completion_tokens": response.usage.completion_tokens if response.usage else None,
                        "total_tokens": response.usage.total_tokens if response.usage else None
                    }
                }
            }

            logger.info(f"规划成功: {planner_output.question}")
            return planner_output, llm_trace

        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise PlannerError(f"LLM调用失败: {e}")

    def plan_with_history(
        self,
        planner_input: PlannerInput
    ) -> tuple[PlannerOutput, list[Dict[str, Any]], Dict[str, Any]]:
        """执行规划并返回重试历史和LLM trace

        Returns:
            (PlannerOutput, retry_history, llm_trace)
        """
        retry_history = []
        error_context = None
        llm_trace = None

        for attempt in range(4):  # 0-3次重试
            try:
                planner_output, llm_trace = self.plan(planner_input, error_context)
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "error": None
                })
                return planner_output, retry_history, llm_trace

            except (json.JSONDecodeError, PlannerError) as e:
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": str(e)
                })
                error_context = str(e)

                if attempt == 3:  # 最后一次重试
                    raise

        raise PlannerError("不应该到达这里")

    async def plan_async(
        self,
        planner_input: PlannerInput,
        error_context: Optional[str] = None
    ) -> tuple[PlannerOutput, Dict[str, Any]]:
        """异步执行规划

        Args:
            planner_input: Planner输入
            error_context: 错误上下文(重试时使用)

        Returns:
            (PlannerOutput, llm_trace)

        Raises:
            PlannerError: 规划失败
        """
        logger.info(f"开始异步规划: {planner_input.chart_type} / {planner_input.language}")

        # 构建Prompt
        prompt = self.build_prompt(planner_input, error_context)

        # 构建完整的messages
        messages = [
            {
                "role": "system",
                "content": self.system_prompt
            },
            {"role": "user", "content": prompt}
        ]

        # 异步调用LLM
        try:
            response = await self.async_client.chat.completions.create(
                model=self.planner_config["model"],
                messages=messages,
                temperature=self.planner_config["temperature"],
                max_tokens=self.planner_config["max_tokens"]
            )

            content = response.choices[0].message.content

            # 检查content是否为空
            if not content or content.strip() == "":
                logger.error(f"LLM返回空响应\nAPI response: {response}")
                raise PlannerError("LLM返回空响应,可能是API限流或内容审查")

            content = content.strip()

            # 移除可能的markdown标记
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 解析JSON
            try:
                output_dict = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失败,尝试使用json_repair修复: {e}")
                try:
                    repaired_content = repair_json(content, return_objects=False)
                    output_dict = json.loads(repaired_content)
                    logger.info("JSON修复成功")
                except Exception as repair_error:
                    logger.error(f"JSON修复失败: {repair_error}\n原始内容: {content[:800]}")
                    raise PlannerError(f"JSON解析失败: {e}")

            # 验证并构建PlannerOutput
            try:
                planner_output = PlannerOutput(**output_dict)
            except Exception as e:
                logger.error(f"PlannerOutput验证失败: {e}\n数据: {output_dict}")
                raise PlannerError(f"输出验证失败: {e}")

            # 构建LLM trace记录
            llm_trace = {
                "model": self.planner_config["model"],
                "temperature": self.planner_config["temperature"],
                "max_tokens": self.planner_config["max_tokens"],
                "messages": messages,
                "response": {
                    "content": content,
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                        "completion_tokens": response.usage.completion_tokens if response.usage else None,
                        "total_tokens": response.usage.total_tokens if response.usage else None
                    }
                }
            }

            logger.info(f"异步规划成功: {planner_output.question}")
            return planner_output, llm_trace

        except Exception as e:
            logger.error(f"异步LLM调用失败: {e}")
            raise PlannerError(f"LLM调用失败: {e}")

    async def plan_with_history_async(
        self,
        planner_input: PlannerInput
    ) -> tuple[PlannerOutput, list[Dict[str, Any]], Dict[str, Any]]:
        """异步执行规划并返回重试历史和LLM trace

        Returns:
            (PlannerOutput, retry_history, llm_trace)
        """
        retry_history = []
        error_context = None
        llm_trace = None

        for attempt in range(4):  # 0-3次重试
            try:
                planner_output, llm_trace = await self.plan_async(planner_input, error_context)
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "error": None
                })
                return planner_output, retry_history, llm_trace

            except (json.JSONDecodeError, PlannerError) as e:
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": str(e)
                })
                error_context = str(e)

                if attempt == 3:  # 最后一次重试
                    raise

        raise PlannerError("不应该到达这里")
