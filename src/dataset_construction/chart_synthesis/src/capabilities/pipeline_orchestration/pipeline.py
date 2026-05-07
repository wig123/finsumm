"""图表合成Pipeline - 编排层"""
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import pandas as pd

from ...models.planner_models import PlannerInput
from ...models.metadata import (
    ChartMetadata, PipelineExecution, LLMExecutionInfo,
    DataSourceInfo, QualityMetrics, ErrorInfo
)
from ...utils.file_manager import OutputFileManager
from ...utils.config_loader import load_chart_mapping
from ..chart_planning import ChartPlanner
from ..dataspec_compilation import DataSpecCompiler
from ..data_fetching import DataFetcher
from ..chart_rendering import ChartRenderer
from ..chart_rendering.frontend_renderer import FrontendRenderer

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Pipeline错误"""
    pass


class ChartSynthesisPipeline:
    """图表合成Pipeline - 协调5层执行"""

    def __init__(self, output_dir: str = "./output"):
        """初始化Pipeline
        
        Args:
            output_dir: 输出目录
        """
        self.base_output_dir = output_dir
        self.file_manager = OutputFileManager(output_dir)
        self.planner = ChartPlanner()
        self.compiler = DataSpecCompiler()
        self.fetcher = DataFetcher()
        self.renderer = ChartRenderer()
        self.frontend_renderer = FrontendRenderer()
        # 加载图表配置，用于检查 synthetic_allowed
        self.chart_mapping = load_chart_mapping().get("chart_types", {})

    def run(self, planner_input: PlannerInput) -> Dict[str, Any]:
        """执行Pipeline

        Args:
            planner_input: Planner输入

        Returns:
            包含chart_id和output_dir的字典
        """
        # 为每个任务创建独立的FileManager实例(线程安全)
        file_manager = OutputFileManager(self.base_output_dir)

        # 创建输出目录
        output_dir = file_manager.create_output_directory(
            planner_input.chart_type,
            planner_input.language,
            planner_input.theme
        )

        chart_id = output_dir.name

        # 初始化metadata
        metadata = ChartMetadata(
            chart_id=chart_id,
            status="in_progress",
            input_config=planner_input.dict()
        )

        # 保存planner输入
        file_manager.save_json(
            "planner_input.json",
            planner_input.dict(),
            subdir="prompts"
        )

        retry_history = {}

        try:
            # === Layer 1: Chart Planning ===
            logger.info("=== Layer 1: Chart Planning ===")
            metadata.current_layer = 1

            start_time = datetime.now()
            planner_output, planner_retries, planner_llm_trace = self.planner.plan_with_history(planner_input)
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 保存planner输出
            file_manager.save_json(
                "planner_output.json",
                planner_output.dict(),
                subdir="prompts"
            )

            # 保存完整的LLM trace (包含prompt和response)
            file_manager.save_json(
                "planner_llm_trace.json",
                planner_llm_trace,
                subdir="prompts"
            )

            # 更新metadata
            metadata.pipeline_execution.planner_llm = LLMExecutionInfo(
                model=self.planner.planner_config["model"],
                duration_ms=duration_ms
            )
            retry_history["layer_1_planner"] = planner_retries

            # === Layer 2: DataSpec Compilation ===
            logger.info("=== Layer 2: DataSpec Compilation ===")
            metadata.current_layer = 2

            dataspec = self.compiler.compile(planner_input, planner_output)

            # 保存dataspec
            file_manager.save_json("dataspec.json", dataspec.dict())

            # === Layer 3: Data Fetching ===
            logger.info("=== Layer 3: Data Fetching ===")
            metadata.current_layer = 3

            # 获取数据（可能是真实数据或模拟数据）
            df, llm_payload, is_synthetic = self.fetcher.fetch_and_build_payload(
                dataspec,
                question=planner_output.question
            )

            # 保存数据
            file_manager.save_csv("raw.csv", df, subdir="data")
            file_manager.save_json("llm_payload.json", llm_payload, subdir="data")

            # 检查是否允许使用合成数据
            chart_config = self.chart_mapping.get(planner_input.chart_type, {})
            synthetic_allowed = chart_config.get("synthetic_allowed", True)  # 默认允许
            if is_synthetic and not synthetic_allowed:
                raise PipelineError(
                    f"图表类型 '{planner_input.chart_type}' 禁止使用合成数据，"
                    f"必须使用真实数据源。请检查数据源配置或更换图表类型。"
                )

            # 更新metadata
            data_source = "Synthetic (LLM Generated)" if is_synthetic else dataspec.what.data_source
            metadata.data_source = DataSourceInfo(
                source=data_source,
                series_code=dataspec.what.series_code if not is_synthetic else "N/A",
                time_range=f"{str(df.index[0])} to {str(df.index[-1])}" if len(df) > 0 else "N/A",
                data_points=len(df)
            )

            # === Layer 4: Chart Rendering ===
            logger.info("=== Layer 4: Chart Rendering ===")
            metadata.current_layer = 4

            start_time = datetime.now()

            # 根据is_frontend标志选择渲染器
            if planner_input.is_frontend:
                # 前端渲染模式
                logger.info(f"使用前端渲染器: {dataspec.library_config.frontend_lib}")
                output_path = str(output_dir / "artifacts" / "chart.png")
                code, html, render_retries, coder_llm_trace = self.frontend_renderer.render_with_retry(
                    dataspec, df, output_path
                )
                # 保存代码和HTML
                file_manager.save_text("code.js", code, subdir="artifacts")
                file_manager.save_text("chart.html", html, subdir="artifacts")
            else:
                # Python渲染模式
                code, figure, render_retries, coder_llm_trace = self.renderer.render_with_retry(dataspec, df)
                # 保存代码和图片
                file_manager.save_text("code.py", code, subdir="artifacts")
                file_manager.save_image("chart.png", figure, subdir="artifacts")

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 更新metadata
            metadata.pipeline_execution.coder_llm = LLMExecutionInfo(
                model=self.renderer.coder_config["model"],
                duration_ms=duration_ms
            )
            retry_history["layer_4_coder"] = render_retries

            # 保存coder输入输出
            # 转换 DataFrame 为可 JSON 序列化的格式
            df_head = df.head(10).reset_index()
            df_head['date'] = df_head['date'].astype(str) if 'date' in df_head.columns else df_head.iloc[:, 0].astype(str)

            file_manager.save_json(
                "coder_input.json",
                {
                    "dataspec": dataspec.dict(),
                    "dataframe_head": df_head.to_dict(orient="records")
                },
                subdir="prompts"
            )
            file_manager.save_json(
                "coder_output.json",
                {"code": code},
                subdir="prompts"
            )

            # 保存Coder LLM Trace
            file_manager.save_json(
                "coder_llm_trace.json",
                coder_llm_trace,
                subdir="prompts"
            )

            # === 完成 ===
            metadata.status = "completed"
            metadata.quality_metrics = QualityMetrics(
                code_executable=True,
                image_generated=True
            )

            logger.info(f"Pipeline执行成功: {chart_id}")

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()

            logger.error(f"Pipeline执行失败 at Layer {metadata.current_layer}: {e}")

            metadata.status = "failed"
            metadata.failed_at_layer = metadata.current_layer
            metadata.error = ErrorInfo(
                type=type(e).__name__,
                message=str(e),
                traceback=error_trace
            )

        finally:
            # 保存metadata和retry_history
            file_manager.save_json("metadata.json", metadata.dict())
            file_manager.save_json(
                "retry_history.json",
                retry_history,
                subdir="logs"
            )

        return {
            "chart_id": chart_id,
            "output_dir": str(output_dir),
            "status": metadata.status
        }

    def batch_run(
        self,
        inputs: List[PlannerInput],
        max_workers: int = 4,
        use_process_pool: bool = False
    ) -> List[Dict[str, Any]]:
        """批量执行Pipeline (支持并发)

        Args:
            inputs: Planner输入列表
            max_workers: 最大并发数 (默认4, 1表示顺序执行)
            use_process_pool: 是否使用进程池 (默认False使用线程池)

        Returns:
            结果列表
        """
        if max_workers == 1:
            # 顺序执行
            return self._batch_run_sequential(inputs)
        else:
            # 并发执行
            return self._batch_run_concurrent(inputs, max_workers, use_process_pool)

    def _batch_run_sequential(
        self,
        inputs: List[PlannerInput]
    ) -> List[Dict[str, Any]]:
        """顺序批量执行"""
        results = []

        for i, planner_input in enumerate(inputs):
            logger.info(f"批量生成进度: {i+1}/{len(inputs)}")

            try:
                result = self.run(planner_input)
                results.append(result)
            except Exception as e:
                logger.error(f"批量生成第{i+1}个失败: {e}")
                results.append({
                    "status": "failed",
                    "error": str(e),
                    "input": planner_input.dict()
                })

        # 统计
        completed = sum(1 for r in results if r.get("status") == "completed")
        failed = sum(1 for r in results if r.get("status") == "failed")

        logger.info(f"批量生成完成: {completed}个成功, {failed}个失败")

        return results

    def _batch_run_concurrent(
        self,
        inputs: List[PlannerInput],
        max_workers: int,
        use_process_pool: bool
    ) -> List[Dict[str, Any]]:
        """并发批量执行"""
        logger.info(f"开始并发批量生成: {len(inputs)}个任务, {max_workers}个worker")

        # 选择执行器
        ExecutorClass = ProcessPoolExecutor if use_process_pool else ThreadPoolExecutor

        results = []
        with ExecutorClass(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_input = {
                executor.submit(self._run_single_task, inp): inp
                for inp in inputs
            }

            # 收集结果
            completed_count = 0
            failed_count = 0

            for future in as_completed(future_to_input):
                planner_input = future_to_input[future]

                try:
                    result = future.result()
                    results.append(result)

                    if result.get("status") == "completed":
                        completed_count += 1
                        logger.info(f"任务完成 ({completed_count}/{len(inputs)}): {result['chart_id']}")
                    else:
                        failed_count += 1
                        logger.warning(f"任务失败 ({failed_count}/{len(inputs)})")

                except Exception as e:
                    failed_count += 1
                    logger.error(f"任务执行异常: {e}")
                    results.append({
                        "status": "failed",
                        "error": str(e),
                        "input": planner_input.dict()
                    })

        logger.info(f"批量生成完成: {completed_count}个成功, {failed_count}个失败")

        return results

    def _run_single_task(self, planner_input: PlannerInput) -> Dict[str, Any]:
        """执行单个任务 (用于并发执行)"""
        try:
            return self.run(planner_input)
        except Exception as e:
            logger.error(f"单任务执行失败: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "input": planner_input.dict()
            }

    async def run_async(self, planner_input: PlannerInput) -> Dict[str, Any]:
        """异步执行Pipeline

        Args:
            planner_input: Planner输入

        Returns:
            包含chart_id和output_dir的字典
        """
        # 为每个任务创建独立的FileManager实例
        file_manager = OutputFileManager(self.base_output_dir)

        # 创建输出目录
        output_dir = file_manager.create_output_directory(
            planner_input.chart_type,
            planner_input.language,
            planner_input.theme
        )

        chart_id = output_dir.name

        # 初始化metadata
        metadata = ChartMetadata(
            chart_id=chart_id,
            status="in_progress",
            input_config=planner_input.dict()
        )

        # 保存planner输入
        await file_manager.save_json_async(
            "planner_input.json",
            planner_input.dict(),
            subdir="prompts"
        )

        retry_history = {}

        try:
            # === Layer 1: Chart Planning (异步) ===
            logger.info("=== Layer 1: Chart Planning (async) ===")
            metadata.current_layer = 1

            start_time = datetime.now()
            planner_output, planner_retries, planner_llm_trace = await self.planner.plan_with_history_async(planner_input)
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 保存planner输出
            await file_manager.save_json_async(
                "planner_output.json",
                planner_output.dict(),
                subdir="prompts"
            )
            await file_manager.save_json_async(
                "planner_llm_trace.json",
                planner_llm_trace,
                subdir="prompts"
            )

            metadata.pipeline_execution.planner_llm = LLMExecutionInfo(
                model=self.planner.planner_config["model"],
                duration_ms=duration_ms
            )
            retry_history["layer_1_planner"] = planner_retries

            # === Layer 2: DataSpec Compilation ===
            logger.info("=== Layer 2: DataSpec Compilation ===")
            metadata.current_layer = 2

            dataspec = self.compiler.compile(planner_input, planner_output)
            await file_manager.save_json_async("dataspec.json", dataspec.dict())

            # === Layer 3: Data Fetching (异步) ===
            logger.info("=== Layer 3: Data Fetching (async) ===")
            metadata.current_layer = 3

            # 获取数据（可能是真实数据或模拟数据）
            df, llm_payload, is_synthetic = await self.fetcher.fetch_and_build_payload_async(
                dataspec,
                question=planner_output.question
            )

            await file_manager.save_csv_async("raw.csv", df, subdir="data")
            await file_manager.save_json_async("llm_payload.json", llm_payload, subdir="data")

            # 更新metadata
            data_source = "Synthetic (LLM Generated)" if is_synthetic else dataspec.what.data_source
            metadata.data_source = DataSourceInfo(
                source=data_source,
                series_code=dataspec.what.series_code if not is_synthetic else "N/A",
                time_range=f"{str(df.index[0])} to {str(df.index[-1])}" if len(df) > 0 else "N/A",
                data_points=len(df)
            )

            # === Layer 4: Chart Rendering (异步) ===
            logger.info("=== Layer 4: Chart Rendering (async) ===")
            metadata.current_layer = 4

            start_time = datetime.now()

            # 根据is_frontend标志选择渲染器
            if planner_input.is_frontend:
                # 前端渲染模式 (异步)
                logger.info(f"使用前端渲染器(异步): {dataspec.library_config.frontend_lib}")
                output_path = str(output_dir / "artifacts" / "chart.png")
                code, html, render_retries, coder_llm_trace = await self.frontend_renderer.render_with_retry_async(
                    dataspec, df, output_path
                )
                # 保存代码和HTML
                await file_manager.save_text_async("code.js", code, subdir="artifacts")
                await file_manager.save_text_async("chart.html", html, subdir="artifacts")
            else:
                # Python渲染模式
                code, figure, render_retries, coder_llm_trace = await self.renderer.render_with_retry_async(dataspec, df)
                # 保存代码和图片
                await file_manager.save_text_async("code.py", code, subdir="artifacts")
                await file_manager.save_image_async("chart.png", figure, subdir="artifacts")

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            metadata.pipeline_execution.coder_llm = LLMExecutionInfo(
                model=self.renderer.coder_config["model"],
                duration_ms=duration_ms
            )
            retry_history["layer_4_coder"] = render_retries

            # 保存coder输入输出
            df_head = df.head(10).reset_index()
            df_head['date'] = df_head['date'].astype(str) if 'date' in df_head.columns else df_head.iloc[:, 0].astype(str)

            await file_manager.save_json_async(
                "coder_input.json",
                {
                    "dataspec": dataspec.dict(),
                    "dataframe_head": df_head.to_dict(orient="records")
                },
                subdir="prompts"
            )
            await file_manager.save_json_async(
                "coder_output.json",
                {"code": code},
                subdir="prompts"
            )
            await file_manager.save_json_async(
                "coder_llm_trace.json",
                coder_llm_trace,
                subdir="prompts"
            )

            # === 完成 ===
            metadata.status = "completed"
            metadata.quality_metrics = QualityMetrics(
                code_executable=True,
                image_generated=True
            )

            logger.info(f"异步Pipeline执行成功: {chart_id}")

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()

            logger.error(f"异步Pipeline执行失败 at Layer {metadata.current_layer}: {e}")

            metadata.status = "failed"
            metadata.failed_at_layer = metadata.current_layer
            metadata.error = ErrorInfo(
                type=type(e).__name__,
                message=str(e),
                traceback=error_trace
            )

        finally:
            # 保存metadata和retry_history
            await file_manager.save_json_async("metadata.json", metadata.dict())
            await file_manager.save_json_async(
                "retry_history.json",
                retry_history,
                subdir="logs"
            )

        return {
            "chart_id": chart_id,
            "output_dir": str(output_dir),
            "status": metadata.status
        }

    async def batch_run_async(
        self,
        inputs: List[PlannerInput],
        max_concurrent: int = 10
    ) -> List[Dict[str, Any]]:
        """异步批量执行Pipeline - 真正的并发

        Args:
            inputs: Planner输入列表
            max_concurrent: 最大并发数

        Returns:
            结果列表
        """
        logger.info(f"开始异步批量生成: {len(inputs)}个任务, max_concurrent={max_concurrent}")

        # 使用信号量限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_with_semaphore(inp):
            async with semaphore:
                try:
                    return await self.run_async(inp)
                except Exception as e:
                    logger.error(f"异步任务执行失败: {e}")
                    return {
                        "status": "failed",
                        "error": str(e),
                        "input": inp.dict()
                    }

        # 并发执行所有任务
        tasks = [run_with_semaphore(inp) for inp in inputs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "status": "failed",
                    "error": str(result),
                    "input": inputs[i].dict()
                })
            else:
                processed_results.append(result)

        # 统计
        completed = sum(1 for r in processed_results if r.get("status") == "completed")
        failed = sum(1 for r in processed_results if r.get("status") == "failed")

        logger.info(f"异步批量生成完成: {completed}个成功, {failed}个失败")

        return processed_results
