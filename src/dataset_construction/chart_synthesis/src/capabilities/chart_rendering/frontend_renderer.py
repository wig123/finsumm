"""前端图表渲染器 - 使用 Playwright 渲染 JavaScript 图表"""
import json
import logging
import re
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import pandas as pd
from openai import OpenAI, AsyncOpenAI

from ...models.dataspec import DataSpec
from ...utils.config_loader import load_llm_config, load_pipeline_config

logger = logging.getLogger(__name__)


# 前端库 CDN 配置
FRONTEND_LIB_CDNS = {
    "echarts": [
        "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"
    ],
    "highcharts": [
        "https://cdn.jsdelivr.net/npm/highcharts@11/highcharts.min.js",
        "https://cdn.jsdelivr.net/npm/highcharts@11/modules/exporting.min.js"
    ],
    "chartjs": [
        "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"
    ],
    "plotlyjs": [
        "https://cdn.plot.ly/plotly-2.27.0.min.js"
    ],
    "d3js": [
        "https://d3js.org/d3.v7.min.js"
    ],
    "tradingview": [
        "https://unpkg.com/lightweight-charts@4/dist/lightweight-charts.standalone.production.js"
    ],
    "recharts": [
        "https://unpkg.com/react@18/umd/react.production.min.js",
        "https://unpkg.com/react-dom@18/umd/react-dom.production.min.js",
        "https://unpkg.com/recharts@2/umd/Recharts.min.js"
    ],
    "antv": [
        "https://unpkg.com/@antv/g2plot@2/dist/g2plot.min.js"
    ],
    "cytoscape": [
        "https://unpkg.com/cytoscape@3/dist/cytoscape.min.js"
    ],
    "sigmajs": [
        "https://unpkg.com/sigma@2/build/sigma.min.js",
        "https://unpkg.com/graphology@0.25/dist/graphology.umd.min.js"
    ]
}


class FrontendRenderError(Exception):
    """前端渲染错误"""
    pass


class FrontendRenderer:
    """前端图表渲染器 - 调用LLM生成JS代码并通过Playwright渲染"""

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
        import yaml
        prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"

        with open(prompts_dir / "frontend_coder_system.txt", "r", encoding="utf-8") as f:
            self.system_prompt = f.read().strip()
        with open(prompts_dir / "frontend_coder_user_template.md", "r", encoding="utf-8") as f:
            self.user_prompt_template = f.read().strip()

        # 加载库特定注意事项配置
        with open(prompts_dir / "library_notes.yaml", "r", encoding="utf-8") as f:
            self.library_notes_config = yaml.safe_load(f)

        # 加载视觉风格注意事项配置
        with open(prompts_dir / "style_notes.yaml", "r", encoding="utf-8") as f:
            self.style_notes_config = yaml.safe_load(f)

    def _get_cdn_scripts(self, library: str) -> str:
        """获取库的 CDN 脚本标签"""
        cdns = FRONTEND_LIB_CDNS.get(library, [])
        return "\n".join(f'<script src="{url}"></script>' for url in cdns)

    def _df_to_json(self, df: pd.DataFrame, max_rows: int = 500) -> str:
        """将 DataFrame 转换为 JSON 格式

        Args:
            df: 数据框
            max_rows: 最大行数，超过时进行采样
        """
        # 如果数据量过大，进行采样
        if len(df) > max_rows:
            logger.info(f"数据量过大 ({len(df)} 行)，采样到 {max_rows} 行")
            # 等间隔采样，保留首尾
            step = len(df) // max_rows
            indices = list(range(0, len(df), step))[:max_rows-1]
            indices.append(len(df) - 1)  # 确保包含最后一个点
            df = df.iloc[indices]

        # 重置索引，将索引作为一列
        df_reset = df.reset_index()
        # 转换为记录格式
        records = df_reset.to_dict(orient='records')
        # 处理日期类型
        for record in records:
            for key, value in record.items():
                if hasattr(value, 'isoformat'):
                    record[key] = value.isoformat()
        return json.dumps(records, ensure_ascii=False, indent=2)

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
        """构建前端 Coder Prompt"""
        library = dataspec.library_config.frontend_lib
        chart_type = dataspec.chart_type
        language_config = dataspec.language_config
        locale = language_config.locale
        visual_style = getattr(dataspec, 'visual_style', 'default')

        # 格式化库特定注意事项
        library_specific_notes = ""
        lib_key = library.lower().replace('.', '').replace('-', '')
        if lib_key in self.library_notes_config:
            config = self.library_notes_config[lib_key]
            library_specific_notes = f"\n\n## **{config['title']}**:\n"
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
            data_json=self._df_to_json(df),
            row_count=len(df),
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
            library_specific_notes=library_specific_notes,
            visual_style_title=visual_style_title,
            visual_style_notes=visual_style_notes
        )

        if error_context:
            prompt += f"\n\n**上次错误**: \n```\n{error_context}\n```\n请修正后重新输出代码。"

        return prompt

    def _generate_code(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        error_context: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """生成前端绑图代码"""
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

            logger.info(f"前端代码生成成功: {len(code)}字符")
            return code, llm_trace

        except Exception as e:
            logger.error(f"前端代码生成失败: {e}")
            raise FrontendRenderError(f"前端代码生成失败: {e}")

    def _extract_code(self, content: str) -> str:
        """提取JavaScript代码"""
        # 移除markdown标记
        if "```javascript" in content:
            match = re.search(r'```javascript\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                return match.group(1).strip()
        elif "```js" in content:
            match = re.search(r'```js\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                return match.group(1).strip()
        elif "```" in content:
            match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                return match.group(1).strip()

        # 如果没有markdown标记,直接返回
        return content.strip()

    def _generate_html(
        self,
        code: str,
        library: str,
        data: pd.DataFrame,
        width: int = 1200,
        height: int = 800
    ) -> str:
        """生成完整的HTML文件"""
        cdn_scripts = self._get_cdn_scripts(library)
        data_json = self._df_to_json(data)

        # 获取库的全局变量名
        lib_globals = {
            "echarts": "echarts",
            "highcharts": "Highcharts",
            "chartjs": "Chart",
            "plotlyjs": "Plotly",
            "d3js": "d3",
            "tradingview": "LightweightCharts",
            "recharts": "Recharts",
            "antv": "G2Plot",
            "cytoscape": "cytoscape",
            "sigmajs": "Sigma"
        }
        lib_global = lib_globals.get(library, library)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chart</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Helvetica Neue', Arial, sans-serif;
            background: #ffffff;
        }}
        #chart-container {{
            width: {width}px;
            height: {height}px;
        }}
    </style>
    {cdn_scripts}
</head>
<body>
    <div id="chart-container"></div>
    <script>
        // 注入数据
        window.chartData = {data_json};

        // 渲染图表
        {code}

        // 等待库加载完成后再调用渲染函数
        function waitForLib(callback, maxWait) {{
            var waited = 0;
            var interval = setInterval(function() {{
                if (typeof {lib_global} !== 'undefined') {{
                    clearInterval(interval);
                    callback();
                }} else {{
                    waited += 100;
                    if (waited >= maxWait) {{
                        clearInterval(interval);
                        document.body.innerHTML = '<pre style="color: red; padding: 20px;">{lib_global} is not defined</pre>';
                    }}
                }}
            }}, 100);
        }}

        waitForLib(function() {{
            try {{
                renderChart('chart-container', window.chartData);
            }} catch (e) {{
                console.error('Chart render error:', e);
                document.body.innerHTML = '<pre style="color: red; padding: 20px;">' + e.message + '</pre>';
            }}
        }}, 10000);
    </script>
</body>
</html>"""
        return html

    async def _render_with_playwright(
        self,
        html_content: str,
        output_path: str,
        width: int = 1200,
        height: int = 800,
        wait_time: int = 3000
    ) -> None:
        """使用 Playwright 渲染 HTML 并截图"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise FrontendRenderError(
                "需要安装 playwright: pip install playwright && playwright install chromium"
            )

        console_logs = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": width, "height": height})

            # 收集控制台日志以便调试
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: console_logs.append(f"[ERROR] {err}"))

            # 使用 set_content 代替 file:// 协议，避免 CDN 跨域问题
            await page.set_content(html_content, wait_until="networkidle")

            # 等待图表容器中出现 SVG 或 Canvas 元素（图表渲染完成的标志）
            try:
                await page.wait_for_selector(
                    "#chart-container svg, #chart-container canvas, .highcharts-root, .echarts-dom",
                    timeout=15000
                )
                logger.info("检测到图表 SVG/Canvas 元素")
            except Exception as e:
                logger.warning(f"等待图表元素超时: {e}")

            # 额外等待动画完成
            await page.wait_for_timeout(wait_time)

            # 检查页面内容（调试用）
            body_content = await page.evaluate("document.body.innerHTML.length")
            logger.info(f"页面 body 内容长度: {body_content}")

            # 检查是否有错误信息
            error_element = await page.query_selector("pre[style*='red']")
            if error_element:
                error_text = await error_element.text_content()
                logger.error(f"页面显示错误: {error_text}")
                if console_logs:
                    logger.error(f"控制台日志: {console_logs[:10]}")
                raise FrontendRenderError(f"图表渲染错误: {error_text}")

            # 截图
            await page.screenshot(path=output_path, full_page=False)

            # 输出控制台日志（如果有错误）
            error_logs = [log for log in console_logs if 'error' in log.lower()]
            if error_logs:
                logger.warning(f"浏览器控制台错误: {error_logs[:5]}")

            await browser.close()

    def render(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        output_path: str,
        error_context: Optional[str] = None
    ) -> Tuple[str, str, Dict[str, Any]]:
        """渲染前端图表

        Args:
            dataspec: DataSpec
            df: 数据
            output_path: 输出图片路径
            error_context: 错误上下文(重试时使用)

        Returns:
            (code, html, llm_trace)
        """
        logger.info(f"开始渲染前端图表: {dataspec.chart_type} with {dataspec.library_config.frontend_lib}")

        # 1. 生成代码
        code, llm_trace = self._generate_code(dataspec, df, error_context)

        # 2. 生成HTML
        library = dataspec.library_config.frontend_lib
        html = self._generate_html(code, library, df)

        # 3. 使用Playwright渲染
        asyncio.run(self._render_with_playwright(html, output_path))

        logger.info(f"前端图表渲染成功: {output_path}")
        return code, html, llm_trace

    async def render_async(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        output_path: str,
        error_context: Optional[str] = None
    ) -> Tuple[str, str, Dict[str, Any]]:
        """异步渲染前端图表

        Args:
            dataspec: DataSpec
            df: 数据
            output_path: 输出图片路径
            error_context: 错误上下文(重试时使用)

        Returns:
            (code, html, llm_trace)
        """
        logger.info(f"开始异步渲染前端图表: {dataspec.chart_type} with {dataspec.library_config.frontend_lib}")

        # 1. 异步生成代码
        code, llm_trace = await self._generate_code_async(dataspec, df, error_context)

        # 2. 生成HTML
        library = dataspec.library_config.frontend_lib
        html = self._generate_html(code, library, df)

        # 3. 使用Playwright渲染
        await self._render_with_playwright(html, output_path)

        logger.info(f"前端图表渲染成功: {output_path}")
        return code, html, llm_trace

    async def _generate_code_async(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        error_context: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """异步生成前端绑图代码"""
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

            logger.info(f"异步前端代码生成成功: {len(code)}字符")
            return code, llm_trace

        except Exception as e:
            logger.error(f"异步前端代码生成失败: {e}")
            raise FrontendRenderError(f"前端代码生成失败: {e}")

    def render_with_retry(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        output_path: str
    ) -> Tuple[str, str, list, Dict[str, Any]]:
        """渲染前端图表并返回重试历史

        Returns:
            (code, html, retry_history, llm_trace)
        """
        retry_history = []
        error_context = None

        for attempt in range(4):  # 0-3次重试
            try:
                code, html, llm_trace = self.render(dataspec, df, output_path, error_context)
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "error": None
                })
                return code, html, retry_history, llm_trace

            except FrontendRenderError as e:
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": str(e)
                })
                error_context = str(e)

                if attempt == 3:
                    raise

        raise FrontendRenderError("不应该到达这里")

    async def render_with_retry_async(
        self,
        dataspec: DataSpec,
        df: pd.DataFrame,
        output_path: str
    ) -> Tuple[str, str, list, Dict[str, Any]]:
        """异步渲染前端图表并返回重试历史

        Returns:
            (code, html, retry_history, llm_trace)
        """
        retry_history = []
        error_context = None

        for attempt in range(4):  # 0-3次重试
            try:
                code, html, llm_trace = await self.render_async(dataspec, df, output_path, error_context)
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "success",
                    "error": None
                })
                return code, html, retry_history, llm_trace

            except FrontendRenderError as e:
                retry_history.append({
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": str(e)
                })
                error_context = str(e)

                if attempt == 3:
                    raise

        raise FrontendRenderError("不应该到达这里")
