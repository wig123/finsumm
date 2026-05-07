"""文件输出管理器"""
import json
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, date
from pandas import Period
from typing import Any, Dict
import uuid
import aiofiles


class OutputFileManager:
    """管理Pipeline输出文件"""

    def __init__(self, base_dir: str = "./output"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.current_output_dir: Path | None = None

    def create_output_directory(
        self,
        chart_type: str,
        language: str,
        theme: str
    ) -> Path:
        """创建输出目录

        Args:
            chart_type: 图表类型
            language: 语言
            theme: 主题

        Returns:
            输出目录路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]

        dir_name = f"{timestamp}_{chart_type}_{language}_{theme}_{short_uuid}"
        output_dir = self.base_dir / dir_name

        # 创建子目录
        (output_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (output_dir / "data").mkdir(parents=True, exist_ok=True)
        (output_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (output_dir / "logs").mkdir(parents=True, exist_ok=True)

        self.current_output_dir = output_dir
        return output_dir

    def save_json(self, filename: str, data: Dict[str, Any], subdir: str = ""):
        """保存JSON文件"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")

        if subdir:
            file_path = self.current_output_dir / subdir / filename
        else:
            file_path = self.current_output_dir / filename

        file_path.parent.mkdir(parents=True, exist_ok=True)

        def json_serial(obj):
            """JSON serializer for datetime/date/Period objects"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, Period):
                return str(obj)
            raise TypeError(f"Type {type(obj)} not serializable")

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=json_serial)

    def save_text(self, filename: str, content: str, subdir: str = ""):
        """保存文本文件"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")

        if subdir:
            file_path = self.current_output_dir / subdir / filename
        else:
            file_path = self.current_output_dir / filename

        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def save_csv(self, filename: str, dataframe, subdir: str = "data"):
        """保存CSV文件"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")

        file_path = self.current_output_dir / subdir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        dataframe.to_csv(file_path, index=True)

    def save_image(self, filename: str, figure, subdir: str = "artifacts"):
        """保存图片文件 - 支持多种图表库"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")

        file_path = self.current_output_dir / subdir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        self._save_figure_by_type(figure, str(file_path))

    def _save_figure_by_type(self, figure, file_path: str):
        """根据figure类型选择保存方式"""
        fig_type = type(figure).__module__

        # matplotlib Figure
        if hasattr(figure, 'savefig'):
            figure.savefig(file_path, dpi=150, bbox_inches='tight')

        # plotly Figure - 使用 kaleido
        elif 'plotly' in fig_type:
            try:
                figure.write_image(file_path, scale=2)
            except Exception:
                html_path = file_path.replace('.png', '.html')
                figure.write_html(html_path)

        # altair Chart - 使用 vl-convert-python (推荐，无需 selenium)
        elif 'altair' in fig_type:
            try:
                # vl-convert-python: ppi=150 提高分辨率
                figure.save(file_path, ppi=150)
            except Exception as e:
                # 如果 vl-convert 失败，尝试保存为 HTML
                html_path = file_path.replace('.png', '.html')
                try:
                    figure.save(html_path)
                except Exception:
                    # 最后尝试保存为 JSON
                    json_path = file_path.replace('.png', '.json')
                    figure.save(json_path)

        # bokeh Figure - 使用 selenium + webdriver-manager
        elif 'bokeh' in fig_type:
            try:
                from bokeh.io import export_png
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service as ChromeService
                from webdriver_manager.chrome import ChromeDriverManager

                # 使用 webdriver-manager 自动管理 chromedriver
                options = webdriver.ChromeOptions()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')

                driver = webdriver.Chrome(
                    service=ChromeService(ChromeDriverManager().install()),
                    options=options
                )
                export_png(figure, filename=file_path, webdriver=driver)
                driver.quit()
            except Exception:
                # 如果 export_png 失败，保存为 HTML
                from bokeh.io import save
                from bokeh.resources import CDN
                html_path = file_path.replace('.png', '.html')
                save(figure, filename=html_path, resources=CDN, title="Bokeh Chart")

        else:
            raise ValueError(f"不支持的figure类型: {fig_type}")

    def get_output_path(self) -> Path:
        """获取当前输出目录路径"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")
        return self.current_output_dir

    # 异步方法
    async def save_json_async(self, filename: str, data: Dict[str, Any], subdir: str = ""):
        """异步保存JSON文件"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")

        if subdir:
            file_path = self.current_output_dir / subdir / filename
        else:
            file_path = self.current_output_dir / filename

        file_path.parent.mkdir(parents=True, exist_ok=True)

        def json_serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, Period):
                return str(obj)
            raise TypeError(f"Type {type(obj)} not serializable")

        json_str = json.dumps(data, ensure_ascii=False, indent=2, default=json_serial)
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json_str)

    async def save_text_async(self, filename: str, content: str, subdir: str = ""):
        """异步保存文本文件"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")

        if subdir:
            file_path = self.current_output_dir / subdir / filename
        else:
            file_path = self.current_output_dir / filename

        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(content)

    async def save_csv_async(self, filename: str, dataframe, subdir: str = "data"):
        """异步保存CSV文件"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")

        file_path = self.current_output_dir / subdir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # pandas to_csv不支持异步,用executor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: dataframe.to_csv(file_path, index=True))

    async def save_image_async(self, filename: str, figure, subdir: str = "artifacts"):
        """异步保存图片文件 - 支持多种图表库"""
        if not self.current_output_dir:
            raise RuntimeError("输出目录未初始化")

        file_path = self.current_output_dir / subdir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 图片保存不支持异步,用executor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._save_figure_by_type(figure, str(file_path))
        )
