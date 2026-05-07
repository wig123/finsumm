"""分步执行器 - 管理单步骤的批量执行"""

import asyncio
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Callable, Any
from tqdm.asyncio import tqdm

from ..models import TaskDefinition
from .step_status_manager import StepStatusManager, StepName, StepResult
from .report_generator import ReportGenerator
from .simplified_pipeline import SimplifiedPipeline

logger = logging.getLogger(__name__)


class StepExecutor:
    """分步执行器

    负责单个步骤的批量并发执行，支持：
    - 任务过滤（跳过已完成/仅重试失败）
    - 并发控制
    - 进度显示
    - 状态记录
    - 报告生成
    """

    def __init__(
        self,
        output_dir: Path,
        max_workers: int = 5,
        batch_size: int = 200
    ):
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.batch_size = batch_size

        # 状态管理
        self.status_manager = StepStatusManager(output_dir)
        self.report_generator = ReportGenerator(output_dir, self.status_manager)

        # Pipeline 实例
        self.pipeline = SimplifiedPipeline(str(output_dir))

        # 任务ID到输出目录的映射 (运行时填充)
        self._task_output_dirs: Dict[str, Path] = {}

    def _get_task_output_dir(self, task: TaskDefinition) -> Path:
        """获取或创建任务输出目录"""
        if task.task_id not in self._task_output_dirs:
            self._task_output_dirs[task.task_id] = self.pipeline.get_task_output_dir(task)
        return self._task_output_dirs[task.task_id]

    async def run_step(
        self,
        step: StepName,
        tasks: List[TaskDefinition],
        retry_failed: bool = False
    ) -> Dict:
        """执行单个步骤

        Args:
            step: 步骤名称 (fetch/render/summarize)
            tasks: 所有任务列表
            retry_failed: 是否仅重试失败的任务

        Returns:
            步骤执行报告
        """
        start_time = datetime.now()

        # 过滤任务
        if retry_failed:
            pending_task_ids = self.status_manager.get_failed_tasks(step, [t.task_id for t in tasks])
            pending_tasks = [t for t in tasks if t.task_id in pending_task_ids]
            logger.info(f"[{step.value.upper()}] 重试模式: {len(pending_tasks)} 个失败任务")
        else:
            # 根据步骤决定前置条件
            if step == StepName.FETCH:
                # Step 2: 无前置条件
                pending_task_ids = self.status_manager.get_pending_tasks(step, [t.task_id for t in tasks])
            elif step == StepName.RENDER:
                # Step 3: 需要 Step 2 成功
                fetch_completed = set(
                    tid for tid in [t.task_id for t in tasks]
                    if self.status_manager.is_step_completed(StepName.FETCH, tid)
                )
                render_pending = self.status_manager.get_pending_tasks(step, [t.task_id for t in tasks])
                pending_task_ids = [tid for tid in render_pending if tid in fetch_completed]
            elif step == StepName.SUMMARIZE:
                # Step 4: 需要 Step 3 成功
                render_completed = set(
                    tid for tid in [t.task_id for t in tasks]
                    if self.status_manager.is_step_completed(StepName.RENDER, tid)
                )
                summary_pending = self.status_manager.get_pending_tasks(step, [t.task_id for t in tasks])
                pending_task_ids = [tid for tid in summary_pending if tid in render_completed]
            else:
                pending_task_ids = []

            pending_tasks = [t for t in tasks if t.task_id in pending_task_ids]

            skipped = len(tasks) - len(pending_tasks)
            logger.info(f"[{step.value.upper()}] 待执行: {len(pending_tasks)} 个任务 (跳过 {skipped} 个)")

        if not pending_tasks:
            logger.info(f"[{step.value.upper()}] 没有待执行的任务")
            return self.status_manager.get_step_statistics(step)

        # 并发执行
        semaphore = asyncio.Semaphore(self.max_workers)

        async def execute_with_semaphore(task: TaskDefinition):
            async with semaphore:
                return await self._execute_single_task(step, task)

        # 使用 tqdm 显示进度
        results = await tqdm.gather(
            *[execute_with_semaphore(t) for t in pending_tasks],
            desc=f"Step {self._step_number(step)}: {step.value}",
            total=len(pending_tasks)
        )

        end_time = datetime.now()

        # 生成报告
        report = self.report_generator.generate_step_report(
            step, tasks, start_time, end_time
        )
        self.report_generator.print_step_summary(step, report)

        return report

    async def _execute_single_task(
        self,
        step: StepName,
        task: TaskDefinition
    ) -> StepResult:
        """执行单个任务的单个步骤"""
        start_time = time.time()

        # 获取任务输出目录
        if step == StepName.FETCH:
            # FETCH 步骤：创建新目录
            output_dir = self._get_task_output_dir(task)
        else:
            # RENDER/SUMMARIZE 步骤：从 FETCH 记录获取已存在的目录
            saved_dir = self.status_manager.get_task_output_dir(task.task_id)
            if saved_dir:
                output_dir = Path(saved_dir)
            else:
                # 回退：尝试创建新目录（可能会导致问题）
                output_dir = self._get_task_output_dir(task)

        try:
            # 根据步骤调用不同方法
            if step == StepName.FETCH:
                result = await self.pipeline.step_fetch_data(task, output_dir)
            elif step == StepName.RENDER:
                result = await self.pipeline.step_render_chart(task, output_dir)
            elif step == StepName.SUMMARIZE:
                result = await self.pipeline.step_generate_summary(task, output_dir)
            else:
                raise ValueError(f"未知步骤: {step}")

            duration = time.time() - start_time

            # 记录结果，FETCH 步骤记录 output_dir
            step_result = StepResult(
                task_id=task.task_id,
                step=step.value,
                status=result["status"],
                duration_seconds=round(duration, 2),
                error=result.get("error"),
                error_type=result.get("error_type"),
                output_dir=str(output_dir) if step == StepName.FETCH else None
            )
            self.status_manager.record_result(step_result)

            return step_result

        except Exception as e:
            duration = time.time() - start_time
            step_result = StepResult(
                task_id=task.task_id,
                step=step.value,
                status="failed",
                duration_seconds=round(duration, 2),
                error=str(e),
                error_type=type(e).__name__,
                output_dir=str(output_dir) if step == StepName.FETCH else None
            )
            self.status_manager.record_result(step_result)
            return step_result

    def _step_number(self, step: StepName) -> int:
        """获取步骤编号"""
        return {
            StepName.FETCH: 2,
            StepName.RENDER: 3,
            StepName.SUMMARIZE: 4
        }[step]

    async def run_all_steps(
        self,
        tasks: List[TaskDefinition],
        skip_summary: bool = False
    ) -> Dict:
        """执行所有步骤 (全流程)"""
        logger.info(f"\n{'='*60}")
        logger.info("全流程执行")
        logger.info(f"{'='*60}")
        logger.info(f"总任务数: {len(tasks)}")
        logger.info(f"并发数: {self.max_workers}")
        logger.info(f"跳过摘要: {skip_summary}")
        logger.info(f"{'='*60}\n")

        # Step 2: Fetch
        fetch_report = await self.run_step(StepName.FETCH, tasks)

        # Step 3: Render
        render_report = await self.run_step(StepName.RENDER, tasks)

        # Step 4: Summarize (可选)
        summary_report = None
        if not skip_summary:
            summary_report = await self.run_step(StepName.SUMMARIZE, tasks)

        # 生成整体报告
        overall_report = self.report_generator.generate_overall_report(tasks)

        return {
            "fetch": fetch_report,
            "render": render_report,
            "summarize": summary_report,
            "overall": overall_report
        }

    def print_status(self, tasks: List[TaskDefinition], step: str = "all"):
        """打印状态摘要"""
        print(f"\n{'='*60}")
        print(f"任务状态摘要")
        print(f"{'='*60}")
        print(f"总任务数: {len(tasks)}")

        if step in ("all", "fetch", "2"):
            stats = self.status_manager.get_step_statistics(StepName.FETCH)
            print(f"\nStep 2 - Fetch:")
            print(f"  已处理: {stats['total_processed']}")
            print(f"  成功: {stats['success']} ({stats['success_rate']})")
            print(f"  失败: {stats['failed']}")

        if step in ("all", "render", "3"):
            stats = self.status_manager.get_step_statistics(StepName.RENDER)
            print(f"\nStep 3 - Render:")
            print(f"  已处理: {stats['total_processed']}")
            print(f"  成功: {stats['success']} ({stats['success_rate']})")
            print(f"  失败: {stats['failed']}")

        if step in ("all", "summarize", "4"):
            stats = self.status_manager.get_step_statistics(StepName.SUMMARIZE)
            print(f"\nStep 4 - Summarize:")
            print(f"  已处理: {stats['total_processed']}")
            print(f"  成功: {stats['success']} ({stats['success_rate']})")
            print(f"  失败: {stats['failed']}")

        print(f"\n{'='*60}")
