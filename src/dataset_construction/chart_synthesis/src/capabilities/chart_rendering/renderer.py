"""图表渲染器 - 代码生成和执行层"""
import json
import logging
import re
import sys
import asyncio
from io import StringIO
from typing import Dict, Any, Optional, Tuple
import pandas as pd
from openai import OpenAI, AsyncOpenAI

from ...models.dataspec import DataSpec
from ...models.coder_models import CoderInput, CoderOutput
from ...utils.config_loader import load_llm_config, load_pipeline_config
from ...utils.retry_decorator import retry_on_failure

logger = logging.getLogger(__name__)


class ChartRenderError(Exception):
    """图表渲染错误"""
    pass


class ChartRenderer:
    """图表渲染器 - 调用Coder LLM生成代码并执行"""

    # 不支持负值的图表类型
    NON_NEGATIVE_CHART_TYPES = ['pie', 'donut', 'treemap', 'sunburst']

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = load_llm_config()

        self.config = config
        self.coder_config = config["pipeline_models"]["coder"]
        self.provider_config = config["providers"][self.coder_config["provider"]]
        self.pipeline_config = load_pipeline_config()

        # 初始化OpenAI客户端（同步和异步）
        self.client = OpenAI(
            api_key=self.provider_config["api_key"],
            base_url=self.provider_config["base_url"]
        )
        self.async_client = AsyncOpenAI(
            api_key=self.provider_config["api_key"],
            base_url=self.provider_config["base_url"]
        )

        # 加载提示词模板
        from pathlib import Path
        import yaml
        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"

        with open(prompts_dir / "coder_system.txt", "r", encoding="utf-8") as f:
            self.system_prompt = f.read().strip()
        with open(prompts_dir / "coder_user_template.md", "r", encoding="utf-8") as f:
            self.user_prompt_template = f.read().strip()

        # 加载库特定注意事项配置
        with open(prompts_dir / "library_notes.yaml", "r", encoding="utf-8") as f:
            self.library_notes_config = yaml.safe_load(f)

        # 加载视觉风格注意事项配置
        with open(prompts_dir / "style_notes.yaml", "r", encoding="utf-8") as f:
            self.style_notes_config = yaml.safe_load(f)

    def _get_style_notes(self, visual_style: str) -> tuple[str, str]:
        """获取视觉风格的标题和注意事项

        Args:
            visual_style: 视觉风格名称

        Returns:
            (style_title, style_notes_text)
        """
        style_config = self.style_notes_config.get(
            visual_style,
            self.style_notes_config.get("default", {})
        )
        style_title = style_config.get("title", "默认专业风格")
        notes = style_config.get("notes", [])
        style_notes_text = "\n".join(f"- {note}" for note in notes)
        return style_title, style_notes_text

    def build_prompt(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        error_context: Optional[str] = None
    ) -> str:
        """构建Coder Prompt"""
        library = dataspec.library_config.python_lib
        chart_type = dataspec.chart_type
        language_config = dataspec.language_config
        locale = language_config.locale
        visual_style = getattr(dataspec, 'visual_style', 'default')

        # 字体配置代码
        font_config_code = "# No font configuration needed for English"
        if locale == "zh-CN":
            fonts = ['PingFang SC', 'Heiti SC', 'STHeiti', 'SimHei', 'Arial Unicode MS']
            font_config_code = f"""# 配置中文字体
import matplotlib
matplotlib.rcParams['font.sans-serif'] = {fonts}
matplotlib.rcParams['axes.unicode_minus'] = False"""

        # 格式化库特定注意事项
        library_specific_notes = ""
        if library in self.library_notes_config:
            config = self.library_notes_config[library]
            library_specific_notes = f"\n\n8. **{config['title']}**:\n"
            for note in config['notes']:
                library_specific_notes += f"   - {note}\n"

        # 获取视觉风格注意事项
        visual_style_title, visual_style_notes = self._get_style_notes(visual_style)

        # 计算统计量 - 优先使用 'value' 列，否则尝试其他数值列
        # 对于特殊图表类型（gantt, sankey, node等），可能没有传统的 value 列
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if 'value' in df.columns:
            value_col = df['value']
        elif numeric_cols:
            # 使用第一个数值列作为替代
            value_col = df[numeric_cols[0]]
        else:
            # 没有数值列时使用占位值（如 gantt 图只有日期和文本）
            value_col = pd.Series([0.0])

        std_value = value_col.std() if len(value_col) > 1 else 0.0
        q01_value = value_col.quantile(0.01) if len(value_col) > 1 else value_col.iloc[0]
        q99_value = value_col.quantile(0.99) if len(value_col) > 1 else value_col.iloc[0]

        # 使用模板填充变量
        prompt = self.user_prompt_template.format(
            library=library,
            chart_type=chart_type,
            dataframe_preview=df.head(10).to_string(),
            row_count=len(df),
            column_names=list(df.columns),
            index_name=df.index.name,
            min_value=f"{value_col.min():.4f}",
            max_value=f"{value_col.max():.4f}",
            mean_value=f"{value_col.mean():.4f}",
            std_value=f"{std_value:.4f}",
            q01_value=f"{q01_value:.4f}",
            q99_value=f"{q99_value:.4f}",
            locale=locale,
            title=language_config.labels.get('title', ''),
            x_label=language_config.labels.get('x_label', ''),
            y_label=language_config.labels.get('y_label', ''),
            font_config_code=font_config_code,
            library_specific_notes=library_specific_notes,
            visual_style_title=visual_style_title,
            visual_style_notes=visual_style_notes
        )

        if error_context:
            prompt += f"\n\n**上次错误**: \n```\n{error_context}\n```\n请修正后重新输出代码。"

        return prompt

    def _preprocess_data_for_chart(
        self,
        df: pd.DataFrame,
        chart_type: str
    ) -> pd.DataFrame:
        """根据图表类型预处理数据
        
        Args:
            df: 原始数据
            chart_type: 图表类型
            
        Returns:
            预处理后的数据
        """
        # 饼图等不支持负值的图表类型：将负值转为绝对值
        if chart_type in self.NON_NEGATIVE_CHART_TYPES:
            df = df.copy()
            numeric_cols = df.select_dtypes(include=['number']).columns
            for col in numeric_cols:
                if (df[col] < 0).any():
                    logger.warning(
                        f"图表类型 {chart_type} 不支持负值，将列 '{col}' 的负值转为绝对值"
                    )
                    df[col] = df[col].abs()
        
        return df

    @retry_on_failure(max_retries=3, exceptions=(ChartRenderError,))
    def render(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        error_context: Optional[str] = None
    ) -> Tuple[str, Any, Dict[str, Any]]:
        """渲染图表

        Args:
            dataspec: DataSpec
            df: 数据
            error_context: 错误上下文(重试时使用)

        Returns:
            (code, figure, llm_trace)
        """
        logger.info(f"开始渲染图表: {dataspec.chart_type}")

        # 0. 数据预处理（处理饼图负值等问题）
        df = self._preprocess_data_for_chart(df, dataspec.chart_type)

        # 1. 生成代码
        code, llm_trace = self._generate_code(dataspec, df, error_context)

        # 2. 执行代码（传入locale用于字体配置）
        locale = dataspec.language_config.locale
        figure = self._execute_code(code, df, locale)

        logger.info("图表渲染成功")
        return code, figure, llm_trace

    def _generate_code(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        error_context: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """生成绘图代码并返回LLM调用trace"""
        prompt = self.build_prompt(dataspec, df, error_context)
        messages = [
            {
                "role": "system",
                "content": self.system_prompt
            },
            {"role": "user", "content": prompt}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.coder_config["model"],
                messages=messages,
                temperature=self.coder_config["temperature"],
                max_tokens=self.coder_config["max_tokens"]
            )

            content = response.choices[0].message.content.strip()

            # 提取代码
            code = self._extract_code(content)

            llm_trace = {
                "model": self.coder_config["model"],
                "temperature": self.coder_config["temperature"],
                "max_tokens": self.coder_config["max_tokens"],
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

            logger.info(f"代码生成成功: {len(code)}字符")
            return code, llm_trace

        except Exception as e:
            logger.error(f"代码生成失败: {e}")
            raise ChartRenderError(f"代码生成失败: {e}")

    def _extract_code(self, content: str) -> str:
        """提取Python代码"""
        # 移除markdown标记
        if "```python" in content:
            match = re.search(r'```python\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                return match.group(1).strip()
        elif "```" in content:
            match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                return match.group(1).strip()

        # 如果没有markdown标记,直接返回
        return content.strip()

    def _fix_common_code_bugs(self, code: str) -> str:
        """修复 LLM 生成代码中的常见 bug
        
        常见问题：
        - mplfinance 的 mav=None（应删除或设为有效值）
        - 未定义的变量
        - 错误的函数调用
        """
        import re
        
        # 修复 mav=None（mplfinance 不接受 None）
        code = re.sub(r',\s*mav\s*=\s*None', '', code)
        code = re.sub(r'mav\s*=\s*None\s*,', '', code)
        
        # 修复 volume=None
        code = re.sub(r',\s*volume\s*=\s*None', '', code)
        code = re.sub(r'volume\s*=\s*None\s*,', '', code)
        
        # 修复 style=None（应使用默认样式）
        code = re.sub(r',\s*style\s*=\s*None', '', code)
        code = re.sub(r'style\s*=\s*None\s*,', '', code)
        
        return code
    
    def _execute_code(self, code: str, df: pd.DataFrame, locale: str = "en-US") -> Any:
        """执行代码生成图表

        Args:
            code: 生成的绑图代码
            df: 数据
            locale: 语言区域设置，用于决定是否配置中文字体
        """
        allowed_imports = self.pipeline_config["code_execution"]["allowed_imports"]
        timeout = self.pipeline_config["code_execution"]["timeout"]

        # 准备执行环境
        exec_globals = {
            "__builtins__": __builtins__,
            "pd": pd,
            "df": df
        }

        # 预导入允许的库
        try:
            import matplotlib
            # 设置非GUI后端,避免在多线程环境中的GUI冲突
            matplotlib.use('Agg')

            # 按需设置中文字体（仅当 locale 为中文时）
            if locale.startswith("zh"):
                matplotlib.rcParams['font.sans-serif'] = [
                    'PingFang SC', 'Heiti SC', 'STHeiti', 'SimHei', 'Arial Unicode MS'
                ]
                matplotlib.rcParams['axes.unicode_minus'] = False

            import matplotlib.pyplot as plt
            import numpy as np

            exec_globals.update({
                "matplotlib": matplotlib,
                "plt": plt,
                "np": np
            })

            # 尝试导入可选库
            try:
                import mplfinance as mpf
                exec_globals["mpf"] = mpf
            except ImportError:
                pass

            try:
                import plotly.graph_objects as go
                import plotly.express as px
                exec_globals["go"] = go
                exec_globals["px"] = px
            except ImportError:
                pass

            try:
                import seaborn as sns
                exec_globals["sns"] = sns
            except ImportError:
                pass

            try:
                import altair as alt
                exec_globals["alt"] = alt
            except ImportError:
                pass

            try:
                from bokeh.plotting import figure as bokeh_figure
                from bokeh.models import ColumnDataSource
                exec_globals["bokeh_figure"] = bokeh_figure
                exec_globals["ColumnDataSource"] = ColumnDataSource
            except ImportError:
                pass

            try:
                import networkx as nx
                exec_globals["nx"] = nx
            except ImportError:
                pass

        except ImportError as e:
            logger.warning(f"导入库失败: {e}")

        # 代码预处理：修复常见 LLM 生成的代码 bug
        code = self._fix_common_code_bugs(code)
        
        # 执行代码
        try:
            exec(code, exec_globals)

            # 调用plot_chart函数
            if "plot_chart" not in exec_globals:
                raise ChartRenderError("代码中未找到plot_chart函数")

            plot_func = exec_globals["plot_chart"]
            figure = plot_func(df)

            return figure

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"代码执行失败:\n{error_trace}")
            raise ChartRenderError(f"代码执行失败:\n{error_trace}")

    def render_with_retry(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame
    ) -> Tuple[str, Any, list, Dict[str, Any]]:
        """渲染图表并返回重试历史

        Returns:
            (code, figure, retry_history, llm_trace)
        """
        retry_history = []
        error_context = None

        for attempt in range(4):  # 0-3次重试
            try:
                code, figure, llm_trace = self.render(dataspec, df, error_context)
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "error": None
                })
                return code, figure, retry_history, llm_trace

            except ChartRenderError as e:
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": str(e)
                })
                error_context = str(e)

                if attempt == 3:
                    raise

        raise ChartRenderError("不应该到达这里")

    async def _generate_code_async(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        error_context: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """异步生成绘图代码"""
        prompt = self.build_prompt(dataspec, df, error_context)
        messages = [
            {
                "role": "system",
                "content": self.system_prompt
            },
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.async_client.chat.completions.create(
                model=self.coder_config["model"],
                messages=messages,
                temperature=self.coder_config["temperature"],
                max_tokens=self.coder_config["max_tokens"]
            )

            content = response.choices[0].message.content.strip()
            code = self._extract_code(content)

            llm_trace = {
                "model": self.coder_config["model"],
                "temperature": self.coder_config["temperature"],
                "max_tokens": self.coder_config["max_tokens"],
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

            logger.info(f"异步代码生成成功: {len(code)}字符")
            return code, llm_trace

        except Exception as e:
            logger.error(f"异步代码生成失败: {e}")
            raise ChartRenderError(f"代码生成失败: {e}")

    async def render_async(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        error_context: Optional[str] = None
    ) -> Tuple[str, Any, Dict[str, Any]]:
        """异步渲染图表

        Args:
            dataspec: DataSpec
            df: 数据
            error_context: 错误上下文(重试时使用)

        Returns:
            (code, figure, llm_trace)
        """
        logger.info(f"开始异步渲染图表: {dataspec.chart_type}")

        # 0. 数据预处理（处理饼图负值等问题）
        df = self._preprocess_data_for_chart(df, dataspec.chart_type)

        # 1. 异步生成代码
        code, llm_trace = await self._generate_code_async(dataspec, df, error_context)

        # 2. 执行代码（CPU密集，放executor，传入locale用于字体配置）
        locale = dataspec.language_config.locale
        loop = asyncio.get_event_loop()
        figure = await loop.run_in_executor(
            None,
            self._execute_code,
            code,
            df,
            locale
        )

        logger.info("异步图表渲染成功")
        return code, figure, llm_trace

    async def render_with_retry_async(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame
    ) -> Tuple[str, Any, list, Dict[str, Any]]:
        """异步渲染图表并返回重试历史

        Returns:
            (code, figure, retry_history, llm_trace)
        """
        retry_history = []
        error_context = None

        for attempt in range(4):  # 0-3次重试
            try:
                code, figure, llm_trace = await self.render_async(dataspec, df, error_context)
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "error": None
                })
                return code, figure, retry_history, llm_trace

            except ChartRenderError as e:
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": str(e)
                })
                error_context = str(e)

                if attempt == 3:
                    raise

        raise ChartRenderError("不应该到达这里")
