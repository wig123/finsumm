"""简化版 Pipeline - 程序化数据选择 + Coder LLM v2"""

import re
import json
import yaml
import random
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Dict, Any

from ..models import TaskDefinition

logger = logging.getLogger(__name__)


class SimplifiedPipeline:
    """简化版 Pipeline - 程序化数据选择 + Coder LLM v2"""

    def __init__(self, output_dir: str = "./output"):
        self.base_output_dir = Path(output_dir)

        # 导入所需组件
        from src.capabilities.data_fetching import DataFetcher
        from src.capabilities.data_fetching.synthetic_generator import SyntheticDataGenerator
        from src.utils.file_manager import OutputFileManager
        from src.utils.config_loader import load_llm_config, load_chart_mapping, load_data_source_mapping
        from openai import AsyncOpenAI

        self.fetcher = DataFetcher()
        self.synthetic_generator = SyntheticDataGenerator()
        self.chart_mapping = load_chart_mapping().get("chart_types", {})
        self.data_source_mapping = load_data_source_mapping()

        # 加载 LLM 配置
        llm_config = load_llm_config()
        self.coder_config = llm_config["pipeline_models"]["coder"]
        provider_config = llm_config["providers"][self.coder_config["provider"]]

        self.async_client = AsyncOpenAI(
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"]
        )

        # 加载 v2 模板
        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
        with open(prompts_dir / "coder_system.txt", "r", encoding="utf-8") as f:
            self.system_prompt = f.read().strip()
        with open(prompts_dir / "coder_user_template_v2.md", "r", encoding="utf-8") as f:
            self.user_prompt_template_v2 = f.read().strip()

        # 加载风格和库注意事项
        with open(prompts_dir / "style_notes.yaml", "r", encoding="utf-8") as f:
            self.style_notes_config = yaml.safe_load(f)
        with open(prompts_dir / "library_notes.yaml", "r", encoding="utf-8") as f:
            self.library_notes_config = yaml.safe_load(f)

    async def run_async(self, task: TaskDefinition) -> Dict[str, Any]:
        """执行简化 Pipeline"""
        from src.utils.file_manager import OutputFileManager
        import pandas as pd

        file_manager = OutputFileManager(str(self.base_output_dir))
        output_dir = file_manager.create_output_directory(
            task.chart_type,
            task.language,
            task.theme
        )
        chart_id = output_dir.name

        try:
            # Layer 1: 跳过 Planner，直接获取数据
            logger.info(f"=== 获取数据: {task.indicator} ({task.data_source}) ===")
            df = await self._fetch_data_async(task)

            # 保存原始数据
            file_manager.save_csv("raw.csv", df, subdir="data")

            # 生成并保存数据摘要 (llm_payload.json)
            llm_payload = self._generate_data_summary(df)
            file_manager.save_json("llm_payload.json", llm_payload, subdir="data")

            # Layer 2: 使用 Coder LLM v2 生成 question + labels + code
            logger.info(f"=== Coder LLM v2: {task.chart_type} ===")
            coder_result = await self._generate_with_coder_v2(task, df)

            # 保存 Coder 结果
            file_manager.save_json("coder_output.json", coder_result, subdir="prompts")

            # Layer 3: 执行代码生成图片
            logger.info(f"=== 执行代码 ===")
            code = coder_result.get('code', '')

            logger.debug(f"代码类型: {type(code)}, 长度: {len(code)}")

            figure = self._execute_code(code, df, task.language)

            # 保存代码到 artifacts 目录
            artifacts_dir = output_dir / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)
            file_manager.save_text("code.py", code, subdir="artifacts")
            file_manager.save_text("chart_code.py", code)

            # 保存图片到 artifacts 目录
            chart_path = artifacts_dir / "chart.png"
            figure.savefig(str(chart_path), dpi=150, bbox_inches='tight',
                          facecolor='white', edgecolor='none')
            import matplotlib.pyplot as plt
            plt.close(figure)

            # 创建 dataspec.json
            dataspec = {
                'chart_type': task.chart_type,
                'language': task.language,
                'theme': task.theme,
                'what': {
                    'data_source': task.data_source,
                    'indicator': task.indicator
                },
                'visual_style': task.visual_style
            }
            file_manager.save_json("dataspec.json", dataspec)

            # 保存元数据
            metadata = {
                'chart_id': chart_id,
                'task_id': task.task_id,
                'chart_type': task.chart_type,
                'theme': task.theme,
                'language': task.language,
                'visual_style': task.visual_style,
                'indicator': task.indicator,
                'data_source': {
                    'name': task.data_source,
                    'data_points': len(df),
                    'time_range': f"{task.time_window_start or 'recent'} - {task.time_window_end or 'now'}"
                },
                'question': coder_result.get('question', ''),
                'labels': coder_result.get('labels', {}),
                'status': 'completed'
            }
            file_manager.save_json("metadata.json", metadata)

            return {
                'status': 'completed',
                'chart_id': chart_id,
                'output_dir': str(output_dir)
            }

        except Exception as e:
            logger.error(f"Pipeline 执行失败: {e}")
            file_manager.save_json("metadata.json", {
                'chart_id': chart_id,
                'task_id': task.task_id,
                'status': 'failed',
                'error': str(e)
            })
            return {
                'status': 'failed',
                'chart_id': chart_id,
                'output_dir': str(output_dir),
                'error': str(e)
            }

    async def _fetch_data_async(self, task: TaskDefinition) -> 'pd.DataFrame':
        """异步获取数据"""
        import pandas as pd

        if task.data_source.lower() == 'synthetic':
            logger.info(f"使用 LLM 生成合成数据: {task.chart_type}/{task.shape}/{task.theme}")
            return await self._generate_synthetic_data_llm(task)

        # 真实数据
        adapter = self.fetcher.adapters.get(task.data_source)
        if adapter is None:
            raise ValueError(f"不支持的数据源: {task.data_source}")

        series_code = self._resolve_series_code(task.indicator, task.data_source)

        # 设置日期范围
        if task.time_window_start and task.time_window_end:
            start_date = datetime.strptime(task.time_window_start, '%Y-%m-%d')
            end_date = datetime.strptime(task.time_window_end, '%Y-%m-%d')
            logger.info(f"使用历史窗口: {task.time_window_start} 到 {task.time_window_end}")
        elif task.time_range_years:
            end_date = datetime.now()
            start_date = end_date - relativedelta(years=task.time_range_years)
            logger.info(f"使用时间范围: 最近 {task.time_range_years} 年")
        else:
            end_date = datetime.now()
            start_date = end_date - relativedelta(years=5)
            logger.info(f"使用默认时间范围: 最近 5 年")

        loop = asyncio.get_event_loop()
        try:
            df = await loop.run_in_executor(
                None,
                lambda: adapter.fetch(
                    series_code=series_code,
                    start=start_date,
                    end=end_date
                )
            )
        except Exception as e:
            logger.warning(f"数据获取异常: {e}，将触发回退")
            df = None

        # 失败自动回退
        if df is None or df.empty:
            fallback_years = random.choice([1, 2, 3, 4, 5])
            logger.warning(f"原始时间范围数据为空，回退到最近 {fallback_years} 年")

            end_date_fallback = datetime.now()
            start_date_fallback = end_date_fallback - relativedelta(years=fallback_years)

            df = await loop.run_in_executor(
                None,
                lambda: adapter.fetch(
                    series_code=series_code,
                    start=start_date_fallback,
                    end=end_date_fallback
                )
            )

            if df is None or df.empty:
                raise ValueError(f"{task.data_source}回退后仍返回空数据: {task.indicator} ({series_code})")

            logger.info(f"回退成功: {len(df)} 行 (最近{fallback_years}年)")
        else:
            logger.info(f"获取数据成功: {len(df)} 行")

        # 如果是 .ts 指标（从 OHLC 提取 close），只保留收盘价
        if task.indicator.endswith('.ts') and 'close' in df.columns:
            logger.info(f"从 OHLC 数据提取 close 列用于时序图表")
            df = df[['close']].copy()
            df.columns = ['value']  # 重命名为通用列名

        return df

    def _resolve_series_code(self, indicator: str, data_source: str) -> str:
        """将 indicator 转换为数据源的 series_code"""
        ds_key = data_source.lower()

        if ds_key in self.data_source_mapping:
            mapping = self.data_source_mapping[ds_key]
            if indicator in mapping:
                resolved = mapping[indicator]
                logger.info(f"指标映射: {indicator} -> {resolved}")
                return resolved

        logger.warning(f"未找到指标映射: {indicator}，直接使用原值")
        return indicator

    async def _generate_synthetic_data_llm(self, task: TaskDefinition) -> 'pd.DataFrame':
        """使用 LLM 生成合成数据"""
        import pandas as pd
        from json_repair import repair_json

        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
        with open(prompts_dir / "synthetic_data_template.md", "r", encoding="utf-8") as f:
            template = f.read()

        desc = task.indicator_description_zh if task.language == 'zh-CN' else task.indicator_description_en
        question = f"生成适合 {task.chart_type} 图表展示的 {task.theme} 主题数据: {desc}"

        prompt = template.format(
            question=question,
            shape=task.shape,
            chart_type=task.chart_type,
            theme=task.theme,
            language=task.language
        )

        try:
            response = await self.async_client.chat.completions.create(
                model=self.coder_config["model"],
                messages=[
                    {"role": "system", "content": "你是一位金融数据专家，擅长生成符合真实世界特征的模拟数据。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            content = response.choices[0].message.content.strip()
            content = content.replace('```json', '').replace('```', '').strip()

            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                result = json.loads(repair_json(content))

            data = result.get('data', result)
            if isinstance(data, list):
                df = pd.DataFrame(data)
                logger.info(f"LLM 合成数据生成成功: {len(df)} 条记录")
                return df
            else:
                raise ValueError(f"无法解析数据: {type(data)}")

        except Exception as e:
            logger.warning(f"LLM 合成数据生成失败: {e}，回退到简单随机数据")
            return self._generate_synthetic_data_fallback(task)

    def _generate_synthetic_data_fallback(self, task: TaskDefinition) -> 'pd.DataFrame':
        """回退：生成简单随机数据"""
        import pandas as pd
        import numpy as np

        shape = task.shape

        if shape == 'CS_1D':
            n = random.choice([5, 6, 7, 8, 10, 12, 15])
            categories = [chr(65 + i) if i < 26 else f'Cat_{i}' for i in range(n)]
            values = np.random.rand(n) * 100
            return pd.DataFrame({'category': categories, 'value': values})
        elif shape == 'CS_ND':
            n = random.choice([6, 8, 10, 12])
            var_count = random.choice([2, 3, 4])
            categories = [f'Cat_{i}' for i in range(n)]
            data = {'category': categories}
            for v in range(var_count):
                data[f'value{v+1}'] = np.random.rand(n) * (100 - v * 20)
            return pd.DataFrame(data)
        elif shape == 'MATRIX':
            n = random.choice([6, 8, 10])
            rows = [f'Row_{i}' for i in range(n)]
            cols = [f'Col_{i}' for i in range(n)]
            data = np.random.rand(n, n) * 100
            return pd.DataFrame(data, index=rows, columns=cols)
        elif shape == 'FLOW':
            n_sources = random.choice([3, 4, 5])
            n_targets = random.choice([3, 4, 5])
            sources = [f'Source_{chr(65+i)}' for i in range(n_sources)] * n_targets
            targets = [f'Target_{i+1}' for _ in range(n_sources) for i in range(n_targets)]
            values = np.random.rand(n_sources * n_targets) * 100
            return pd.DataFrame({'source': sources, 'target': targets, 'value': values})
        else:
            n = random.choice([100, 150, 200, 250, 300])
            dates = pd.date_range(start='2020-01-01', periods=n, freq='D')
            values = np.cumsum(np.random.randn(n)) + 100
            return pd.DataFrame({'date': dates, 'value': values}).set_index('date')

    def _generate_data_summary(self, df: 'pd.DataFrame') -> Dict:
        """生成数据摘要 (llm_payload.json)"""
        import pandas as pd
        import numpy as np

        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if not numeric_cols:
            return {"type": "empty", "repr": {}}

        if 'value' in df.columns:
            value_col = df['value']
        elif 'close' in df.columns:
            value_col = df['close']
        elif 'Close' in df.columns:
            value_col = df['Close']
        else:
            value_col = df[numeric_cols[0]]

        try:
            max_idx = value_col.idxmax()
            min_idx = value_col.idxmin()
            last_idx = value_col.index[-1] if len(value_col) > 0 else None

            summary = {
                "type": "repr_with_recent",
                "repr": {
                    "max_value": float(value_col.max()),
                    "max_date": str(max_idx),
                    "min_value": float(value_col.min()),
                    "min_date": str(min_idx),
                    "last_value": float(value_col.iloc[-1]) if len(value_col) > 0 else None,
                    "last_date": str(last_idx),
                    "mean": float(value_col.mean()),
                    "std": float(value_col.std()) if len(value_col) > 1 else 0.0,
                    "n_points": len(value_col)
                },
                "recent_raw": {}
            }

            recent_n = min(5, len(value_col))
            for i in range(-recent_n, 0):
                idx = value_col.index[i]
                summary["recent_raw"][str(idx)] = float(value_col.iloc[i])

            return summary
        except Exception as e:
            return {"type": "error", "error": str(e)}

    async def _generate_with_coder_v2(self, task: TaskDefinition, df: 'pd.DataFrame') -> Dict:
        """使用 Coder LLM v2 生成 question + labels + code"""
        import pandas as pd
        import random

        chart_config = self.chart_mapping.get(task.chart_type, {})
        # 从配置的 python_libs 列表中随机选择一个库
        python_libs = chart_config.get('python_libs', ['matplotlib'])
        # 过滤掉依赖不完整的库
        available_libs = self._filter_available_libs(python_libs)
        library = random.choice(available_libs) if available_libs else 'matplotlib'

        style_config = self.style_notes_config.get(task.visual_style, self.style_notes_config.get('default', {}))
        style_title = style_config.get('title', '默认风格')
        style_notes = "\n".join(f"- {note}" for note in style_config.get('notes', []))

        library_notes = ""
        if library in self.library_notes_config:
            lib_config = self.library_notes_config[library]
            library_notes = f"\n\n### {lib_config['title']}\n"
            for note in lib_config['notes']:
                library_notes += f"- {note}\n"

        # 读取图表类型专属约束
        data_constraints = chart_config.get('data_constraints', [])
        chart_constraints = ""
        if data_constraints:
            chart_constraints = f"\n\n## {task.chart_type} 图表约束\n"
            for constraint in data_constraints:
                chart_constraints += f"- {constraint}\n"

        # 根据库类型和语言生成字体配置代码
        font_config_code = "# No font configuration needed"
        if task.language == "zh-CN":
            fonts = ['PingFang SC', 'Heiti SC', 'STHeiti', 'SimHei', 'Arial Unicode MS']
            if library in ['matplotlib', 'seaborn', 'mplfinance', 'networkx']:
                font_config_code = f"""import matplotlib
matplotlib.rcParams['font.sans-serif'] = {fonts}
matplotlib.rcParams['axes.unicode_minus'] = False"""
            elif library == 'plotly':
                font_config_code = """# 在返回 figure 之前添加字体配置:
# fig.update_layout(font=dict(family='PingFang SC, Heiti SC, STHeiti, SimHei, Arial Unicode MS, sans-serif'))"""
            elif library == 'altair':
                font_config_code = """# 在返回 chart 之前添加字体配置 (见 library_notes)"""
            elif library == 'bokeh':
                font_config_code = """# Bokeh 需要为每个文本元素单独设置字体 (见 library_notes)"""

        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if 'value' in df.columns:
            value_col = df['value']
        elif numeric_cols:
            value_col = df[numeric_cols[0]]
        else:
            value_col = pd.Series([0.0])

        indicator_desc = task.indicator_description_zh if task.language == 'zh-CN' else task.indicator_description_en

        # 计算时间范围（针对时序数据）
        time_start = "N/A"
        time_end = "N/A"
        time_span_days = 0
        if hasattr(df.index, 'min') and hasattr(df.index, 'max'):
            try:
                idx_min, idx_max = df.index.min(), df.index.max()
                time_start = str(idx_min.date()) if hasattr(idx_min, 'date') else str(idx_min)
                time_end = str(idx_max.date()) if hasattr(idx_max, 'date') else str(idx_max)
                if hasattr(idx_max - idx_min, 'days'):
                    time_span_days = (idx_max - idx_min).days
            except Exception:
                pass

        # 时序数据变换建议（30%概率触发）
        transform_hint = ""
        is_ts_data = task.shape.startswith("TS") if hasattr(task, 'shape') else False
        # OHLC 图表类型不适合做数据变换
        ohlc_charts = {'candlestick', 'candlestick_volume', 'candlestick_indicator', 'ohlc', 'bollinger_bands', 'ichimoku_cloud', 'renko', 'point_figure', 'volume_profile', 'market_depth'}
        if is_ts_data and task.chart_type not in ohlc_charts and random.random() < 0.3:
            logger.info(f"[RENDER] {task.task_id}: 触发数据变换建议")
            transform_hint = """
## 数据预处理建议 (可选)
为了增加分析视角的多样性，你可以考虑对原始数据进行预处理：
- **收益率**: `df['value'].pct_change()` — 展示波动特征和收益分布
- **移动平均**: `df['value'].rolling(window=N).mean()` — 平滑短期噪声
- **累计变化**: `df['value'].cumsum()` 或基于基期的累计收益
- **标准化**: `(df['value'] - df['value'].mean()) / df['value'].std()` — 便于跨指标对比

如果进行了预处理，请确保标题、轴标签准确反映变换后的数据含义。"""

        prompt = self.user_prompt_template_v2.format(
            library=library,
            chart_type=task.chart_type,
            indicator=task.indicator,
            indicator_description=indicator_desc,
            data_source=task.data_source,
            theme=task.theme,
            locale=task.language,
            dataframe_preview=df.head(10).to_string(),
            row_count=len(df),
            column_names=list(df.columns),
            index_name=df.index.name or 'None',
            time_start=time_start,
            time_end=time_end,
            time_span_days=time_span_days,
            min_value=f"{value_col.min():.4f}",
            max_value=f"{value_col.max():.4f}",
            mean_value=f"{value_col.mean():.4f}",
            std_value=f"{value_col.std():.4f}" if len(value_col) > 1 else "0.0",
            q01_value=f"{value_col.quantile(0.01):.4f}" if len(value_col) > 1 else f"{value_col.iloc[0]:.4f}",
            q99_value=f"{value_col.quantile(0.99):.4f}" if len(value_col) > 1 else f"{value_col.iloc[0]:.4f}",
            font_config_code=font_config_code,
            library_specific_notes=library_notes,
            visual_style_title=style_title,
            visual_style_notes=style_notes,
            transform_hint=transform_hint,
            chart_constraints=chart_constraints
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt}
        ]

        response = await self.async_client.chat.completions.create(
            model=self.coder_config["model"],
            messages=messages,
            temperature=self.coder_config["temperature"],
            max_tokens=self.coder_config["max_tokens"]
        )

        content = response.choices[0].message.content.strip()
        return self._parse_coder_v2_output(content)

    def _parse_coder_v2_output(self, content: str) -> Dict:
        """解析 Coder v2 的 JSON 输出"""
        from json_repair import repair_json

        try:
            content = re.sub(r'^```json\s*', '', content, flags=re.MULTILINE)
            content = re.sub(r'^```\s*$', '', content, flags=re.MULTILINE)
            content = content.strip()

            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 解析失败，尝试修复: {e}")
                fixed_content = repair_json(content)
                result = json.loads(fixed_content)

            # 修复双重转义
            if 'code' in result:
                code = result['code']
                if isinstance(code, str) and '\n' not in code and '\\n' in code:
                    logger.warning("检测到双重转义，正在修复...")
                    code = code.replace('\\\\', '\x00')
                    code = code.replace('\\n', '\n')
                    code = code.replace('\\t', '\t')
                    code = code.replace('\\"', '"')
                    code = code.replace("\\'", "'")
                    code = code.replace('\x00', '\\')
                    result['code'] = code
                    logger.debug(f"修复后代码前100字符: {repr(code[:100])}")

            if 'code' not in result:
                raise ValueError("JSON 缺少 'code' 字段")

            if 'question' not in result:
                result['question'] = 'Data Analysis Question'
            if 'labels' not in result:
                result['labels'] = {
                    'title': 'Chart Title',
                    'x_label': 'X',
                    'y_label': 'Y'
                }

            return result

        except Exception as e:
            logger.warning(f"JSON 解析完全失败: {e}，尝试提取代码")

        code_match = re.search(r'```python\s*(.*?)\s*```', content, re.DOTALL)
        if code_match:
            code = code_match.group(1)
        else:
            code = content

        return {
            'question': 'Auto-generated question',
            'labels': {
                'title': 'Chart',
                'x_label': 'X',
                'y_label': 'Y'
            },
            'code': code
        }

    def _execute_code(self, code: str, df: 'pd.DataFrame', locale: str) -> Any:
        """执行生成的代码，支持多种绑图库"""
        import pandas as pd
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        code = code.strip()
        if code.startswith('\ufeff'):
            code = code[1:]

        code = self._fix_common_bugs(code)

        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            logger.error(f"❌ 代码语法错误: {e}")
            lines = code.split('\n')[:10]
            for i, line in enumerate(lines, 1):
                logger.error(f"  行{i}: {repr(line)}")
            raise ValueError(f"代码语法错误: {e}") from e

        exec_globals = {
            "__builtins__": __builtins__,
            "df": df.copy(),
            "pd": pd,
            "plt": plt,
            "np": np,
            "matplotlib": matplotlib
        }

        # 尝试导入各种绘图库
        try:
            import mplfinance as mpf
            exec_globals["mpf"] = mpf
        except ImportError:
            pass

        try:
            import seaborn as sns
            exec_globals["sns"] = sns
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

        exec(code, exec_globals)

        if "plot_chart" not in exec_globals:
            raise ValueError("代码中未找到 plot_chart 函数")

        result = exec_globals["plot_chart"](df)

        # 处理不同库的返回类型，统一转换为 matplotlib Figure
        figure = self._normalize_figure(result)
        return figure

    def _normalize_figure(self, result: Any) -> 'matplotlib.figure.Figure':
        """将不同库的返回结果统一转换为 matplotlib Figure"""
        import matplotlib.pyplot as plt
        import matplotlib.figure

        # 已经是 matplotlib Figure
        if isinstance(result, matplotlib.figure.Figure):
            return result

        # Axes 对象 (seaborn 等返回)
        if hasattr(result, 'figure') and isinstance(result.figure, matplotlib.figure.Figure):
            return result.figure

        # 元组 (mplfinance 返回 (fig, axes))
        if isinstance(result, tuple) and len(result) >= 1:
            if isinstance(result[0], matplotlib.figure.Figure):
                return result[0]

        # Plotly Figure
        try:
            import plotly.graph_objects as go
            if isinstance(result, go.Figure):
                return self._plotly_to_matplotlib(result)
        except ImportError:
            pass

        # Altair Chart
        try:
            import altair as alt
            if isinstance(result, (alt.Chart, alt.LayerChart, alt.HConcatChart, alt.VConcatChart)):
                return self._altair_to_matplotlib(result)
        except ImportError:
            pass

        # Bokeh Figure (多种可能的类型)
        try:
            from bokeh.plotting import figure as bokeh_figure_func
            from bokeh.plotting._figure import figure as BokehFigureLower
            if isinstance(result, BokehFigureLower):
                return self._bokeh_to_matplotlib(result)
        except ImportError:
            pass
        try:
            # 备用检测方法：检查类名
            if type(result).__module__.startswith('bokeh') and 'figure' in type(result).__name__.lower():
                return self._bokeh_to_matplotlib(result)
        except Exception:
            pass

        # 无法识别的类型
        raise ValueError(f"无法处理的返回类型: {type(result)}")

    def _plotly_to_matplotlib(self, fig) -> 'matplotlib.figure.Figure':
        """将 Plotly Figure 转换为 matplotlib Figure"""
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        import io

        try:
            # 使用 kaleido 导出为 PNG 字节流
            img_bytes = fig.to_image(format="png", width=1200, height=800, scale=2)
            img = mpimg.imread(io.BytesIO(img_bytes))

            mpl_fig, ax = plt.subplots(figsize=(12, 8))
            ax.imshow(img)
            ax.axis('off')
            mpl_fig.tight_layout(pad=0)
            return mpl_fig
        except Exception as e:
            raise ValueError(f"Plotly 转换失败 (需要安装 kaleido): {e}")

    def _altair_to_matplotlib(self, chart) -> 'matplotlib.figure.Figure':
        """将 Altair Chart 转换为 matplotlib Figure"""
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        import tempfile
        import os

        try:
            # 使用 chart.save() 导出为临时 PNG 文件
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name

            chart.save(tmp_path, scale_factor=2)
            img = mpimg.imread(tmp_path)
            os.unlink(tmp_path)

            mpl_fig, ax = plt.subplots(figsize=(12, 8))
            ax.imshow(img)
            ax.axis('off')
            mpl_fig.tight_layout(pad=0)
            return mpl_fig
        except Exception as e:
            raise ValueError(f"Altair 转换失败 (需要安装 vl-convert-python): {e}")

    def _bokeh_to_matplotlib(self, fig) -> 'matplotlib.figure.Figure':
        """将 Bokeh Figure 转换为 matplotlib Figure"""
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        import io

        try:
            from bokeh.io import export_png
            import tempfile
            import os

            # 导出为临时 PNG 文件
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name

            export_png(fig, filename=tmp_path)
            img = mpimg.imread(tmp_path)
            os.unlink(tmp_path)

            mpl_fig, ax = plt.subplots(figsize=(12, 8))
            ax.imshow(img)
            ax.axis('off')
            mpl_fig.tight_layout(pad=0)
            return mpl_fig
        except Exception as e:
            raise ValueError(f"Bokeh 转换失败 (需要安装 selenium 和 chromedriver): {e}")

    def _filter_available_libs(self, libs: list) -> list:
        """过滤掉依赖不完整的库，返回可用库列表"""
        if not hasattr(self, '_lib_availability_cache'):
            self._lib_availability_cache = {}

        available = []
        for lib in libs:
            if lib in self._lib_availability_cache:
                if self._lib_availability_cache[lib]:
                    available.append(lib)
                continue

            is_available = self._check_lib_availability(lib)
            self._lib_availability_cache[lib] = is_available
            if is_available:
                available.append(lib)
            else:
                logger.debug(f"库 {lib} 依赖不完整，已跳过")

        return available

    def _check_lib_availability(self, lib: str) -> bool:
        """检查特定库是否可用（包括其导出依赖）"""
        # 基础库总是可用（只要能导入）
        basic_libs = ['matplotlib', 'seaborn', 'mplfinance', 'networkx']
        if lib in basic_libs:
            try:
                __import__(lib if lib != 'mplfinance' else 'mplfinance')
                return True
            except ImportError:
                return False

        # Plotly 需要 kaleido
        if lib == 'plotly':
            try:
                import plotly.graph_objects as go
                # 测试 kaleido 是否可用
                fig = go.Figure()
                fig.to_image(format="png", width=100, height=100)
                return True
            except Exception:
                return False

        # Altair 需要 vl-convert (通过 chart.save() 测试)
        if lib == 'altair':
            try:
                import altair as alt
                import pandas as pd
                import tempfile
                import os

                # 测试 vl-convert 是否可用
                df = pd.DataFrame({'x': [1], 'y': [1]})
                chart = alt.Chart(df).mark_point().encode(x='x', y='y')
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    tmp_path = tmp.name
                chart.save(tmp_path)
                os.unlink(tmp_path)
                return True
            except Exception:
                return False

        # Bokeh 需要 selenium + browser driver
        if lib == 'bokeh':
            try:
                from bokeh.plotting import figure
                from bokeh.io import export_png
                import tempfile
                import os

                # 测试 export_png 是否可用
                p = figure(width=100, height=100)
                p.line([0, 1], [0, 1])
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    tmp_path = tmp.name
                export_png(p, filename=tmp_path)
                os.unlink(tmp_path)
                return True
            except Exception:
                return False

        # 未知库，假设可用
        return True

    def _fix_common_bugs(self, code: str) -> str:
        """修复 LLM 生成代码的常见 bug"""
        code = re.sub(
            r'from matplotlib\.ticker import (\w+, )*AutoDateLocator',
            r'from matplotlib.dates import AutoDateLocator',
            code
        )

        code = re.sub(
            r'(import matplotlib\n)+',
            'import matplotlib\n',
            code
        )

        return code

    # ========== 分步执行方法 ==========

    async def step_fetch_data(self, task: TaskDefinition, output_dir: Path) -> Dict[str, Any]:
        """Step 2: 仅获取/生成数据

        Args:
            task: 任务定义
            output_dir: 任务输出目录 (已存在)

        Returns:
            {"status": "success/failed", "data_path": str, "row_count": int, "error": str?}
        """
        import pandas as pd
        from src.utils.file_manager import OutputFileManager

        data_dir = output_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"[FETCH] {task.task_id}: {task.indicator} ({task.data_source})")
            df = await self._fetch_data_async(task)

            # 保存原始数据
            data_path = data_dir / "raw.csv"
            df.to_csv(data_path)

            # 生成并保存数据摘要
            llm_payload = self._generate_data_summary(df)
            with open(data_dir / "llm_payload.json", "w", encoding="utf-8") as f:
                json.dump(llm_payload, f, ensure_ascii=False, indent=2)

            # 创建 dataspec.json (供 generate_summary 使用)
            dataspec = {
                "chart_type": task.chart_type,
                "language": task.language,
                "shape": task.shape,
                "theme": task.theme,
                "what": {
                    "indicator_id": task.indicator,
                    "data_source": task.data_source,
                    "series_code": getattr(task, 'series_code', task.indicator)
                }
            }
            with open(output_dir / "dataspec.json", "w", encoding="utf-8") as f:
                json.dump(dataspec, f, ensure_ascii=False, indent=2)

            logger.info(f"[FETCH] {task.task_id}: 成功 ({len(df)} 行)")
            return {
                "status": "success",
                "data_path": str(data_path),
                "row_count": len(df)
            }

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"[FETCH] {task.task_id}: 失败 - {error_type}: {error_msg}")
            return {
                "status": "failed",
                "error": error_msg,
                "error_type": error_type
            }

    async def step_render_chart(self, task: TaskDefinition, output_dir: Path) -> Dict[str, Any]:
        """Step 3: 仅渲染图表 (需要已获取的数据)

        Args:
            task: 任务定义
            output_dir: 任务输出目录 (已存在，包含 data/raw.csv)

        Returns:
            {"status": "success/failed", "chart_path": str, "error": str?}
        """
        import pandas as pd

        data_path = output_dir / "data" / "raw.csv"
        artifacts_dir = output_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 加载数据
            if not data_path.exists():
                raise FileNotFoundError(f"数据文件不存在: {data_path}")

            df = pd.read_csv(data_path, index_col=0, parse_dates=True)
            logger.info(f"[RENDER] {task.task_id}: 加载数据 ({len(df)} 行)")

            # Coder LLM 生成代码
            logger.info(f"[RENDER] {task.task_id}: Coder LLM 生成代码...")
            coder_result = await self._generate_with_coder_v2(task, df)

            # 保存 Coder 结果
            prompts_dir = output_dir / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            with open(prompts_dir / "coder_output.json", "w", encoding="utf-8") as f:
                json.dump(coder_result, f, ensure_ascii=False, indent=2)

            # 执行代码
            code = coder_result.get('code', '')
            logger.info(f"[RENDER] {task.task_id}: 执行代码...")
            figure = self._execute_code(code, df, task.language)

            # 保存代码
            with open(artifacts_dir / "code.py", "w", encoding="utf-8") as f:
                f.write(code)

            # 保存图片
            chart_path = artifacts_dir / "chart.png"
            figure.savefig(str(chart_path), dpi=150, bbox_inches='tight',
                          facecolor='white', edgecolor='none')
            import matplotlib.pyplot as plt
            plt.close(figure)

            # 保存元数据 (兼容 v3 格式)
            # 获取数据信息
            time_range = 'unknown'
            data_points = len(df)
            if hasattr(df.index, 'min') and hasattr(df.index, 'max'):
                try:
                    time_range = f"{df.index.min()} to {df.index.max()}"
                except Exception:
                    pass

            metadata = {
                'chart_id': output_dir.name,
                'task_id': task.task_id,
                'chart_type': task.chart_type,
                'theme': task.theme,
                'language': task.language,
                'visual_style': task.visual_style,
                'indicator': task.indicator,
                # data_source 作为字典，兼容 v3 generate_summary
                'data_source': {
                    'source': task.data_source,
                    'series_code': getattr(task, 'series_code', task.indicator),
                    'time_range': time_range,
                    'data_points': data_points
                },
                'question': coder_result.get('question', ''),
                'labels': coder_result.get('labels', {}),
                'status': 'rendered'
            }
            with open(output_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"[RENDER] {task.task_id}: 成功")
            return {
                "status": "success",
                "chart_path": str(chart_path),
                "question": coder_result.get('question', ''),
                "labels": coder_result.get('labels', {})
            }

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"[RENDER] {task.task_id}: 失败 - {error_type}: {error_msg}")
            return {
                "status": "failed",
                "error": error_msg,
                "error_type": error_type
            }

    async def step_generate_summary(self, task: TaskDefinition, output_dir: Path) -> Dict[str, Any]:
        """Step 4: 仅生成摘要 (需要已渲染的图表)

        使用 v3 的 generate_summary.process_chart 方法生成专业的四层分析报告。

        Args:
            task: 任务定义
            output_dir: 任务输出目录 (已存在，包含 artifacts/chart.png)

        Returns:
            {"status": "success/failed", "summary_path": str, "error": str?}
        """
        import sys
        from pathlib import Path as PathlibPath

        # 添加 scripts 目录到路径以便导入 generate_summary
        scripts_dir = PathlibPath(__file__).parent.parent.parent.parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        try:
            from generate_summary import process_chart

            logger.info(f"[SUMMARY] {task.task_id}: 生成摘要...")

            # 调用 v3 的 process_chart 方法
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: process_chart(output_dir)
            )

            # 更新元数据状态
            metadata_path = output_dir / "metadata.json"
            if metadata_path.exists():
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                metadata['status'] = 'complete'
                metadata['summary'] = result.get('analysis', '')[:500]  # 截取前500字符作为摘要
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"[SUMMARY] {task.task_id}: 成功")
            return {
                "status": "success",
                "summary_path": str(output_dir / "summary" / "result.json")
            }

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"[SUMMARY] {task.task_id}: 失败 - {error_type}: {error_msg}")
            return {
                "status": "failed",
                "error": error_msg,
                "error_type": error_type
            }

    def get_task_output_dir(self, task: TaskDefinition) -> Path:
        """获取任务的输出目录"""
        from src.utils.file_manager import OutputFileManager
        file_manager = OutputFileManager(str(self.base_output_dir))
        return file_manager.create_output_directory(
            task.chart_type,
            task.language,
            task.theme
        )
