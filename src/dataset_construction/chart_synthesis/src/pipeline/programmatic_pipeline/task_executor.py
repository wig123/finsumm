"""任务执行器 v2 - 支持分批目录 + Summary 生成 + 重试"""

import re
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from collections import defaultdict
from typing import List, Dict, Any

from ..models import TaskDefinition, TaskResult
from .progress_manager import ProgressManager
from .simplified_pipeline import SimplifiedPipeline

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器 v2 - 支持分批目录 + Summary 生成 + 重试"""

    def __init__(
        self,
        output_dir: Path,
        batch_size: int = 200,
        max_workers: int = 5,
        max_retries: int = 3,
        generate_summary: bool = True,
        total_tasks: int = 0
    ):
        self.output_dir = Path(output_dir)
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.generate_summary = generate_summary
        self.total_tasks = total_tasks
        self.progress = ProgressManager(output_dir)

        # 摘要输出目录
        self.summary_output_dir = self.output_dir / "summaries"
        if generate_summary:
            self.summary_output_dir.mkdir(parents=True, exist_ok=True)

        # 摘要计数器（从已有目录恢复最大索引）
        self._summary_counter = self._get_max_summary_index()
        self._summary_lock = asyncio.Lock()

        # Summary 异步队列（后台并行处理）
        self._summary_queue: asyncio.Queue = None
        self._summary_workers: List[asyncio.Task] = []
        self._summary_worker_count = max_workers

        if self._summary_counter > 0:
            logger.info(f"从已有摘要恢复计数: {self._summary_counter}")

    def _get_max_summary_index(self) -> int:
        """从已有的 summaries 目录中获取最大索引"""
        if not self.summary_output_dir.exists():
            return 0

        max_index = 0
        pattern = re.compile(r'^(\d+)_')

        for item in self.summary_output_dir.iterdir():
            if item.is_dir():
                match = pattern.match(item.name)
                if match:
                    index = int(match.group(1))
                    if index > max_index:
                        max_index = index

        return max_index

    async def run_all(self, tasks: List[TaskDefinition], retry_failed: bool = False):
        """执行所有任务"""
        # 过滤任务
        if retry_failed:
            pending_tasks = [t for t in tasks if self.progress.is_failed(t.task_id)]
            logger.info(f"重试模式: {len(pending_tasks)} 个失败任务")
        else:
            pending_tasks = [t for t in tasks if not self.progress.is_completed(t.task_id)]
            logger.info(f"待执行: {len(pending_tasks)} 个任务 (已跳过 {len(tasks) - len(pending_tasks)} 个已完成)")

        if not pending_tasks:
            logger.info("没有待执行的任务")
            return

        logger.info(f"\n{'='*60}")
        logger.info(f"高并发执行")
        logger.info(f"{'='*60}")
        logger.info(f"总任务数: {len(pending_tasks)} 个 ({self.max_workers}并发)")
        logger.info(f"生成摘要: {'是' if self.generate_summary else '否'}")
        logger.info(f"{'='*60}")

        # 更新总任务数
        self.total_tasks = len(tasks)

        # 启动 Summary workers
        await self._start_summary_workers()

        try:
            await self._run_task_group(pending_tasks)
        finally:
            # 等待所有 Summary 任务完成
            await self._wait_summary_completion()

        # 打印总结
        stats = self.progress.get_stats()
        logger.info(f"\n{'='*60}")
        logger.info(f"全部执行完成")
        logger.info(f"总计: {stats['completed']} 已完成, {stats['failed']} 失败")
        logger.info(f"{'='*60}")

    async def _run_task_group(self, tasks: List[TaskDefinition]):
        """执行一组任务（按 batch 分组）"""
        # 按 batch 分组
        batches = defaultdict(list)
        for task in tasks:
            batches[task.batch_index].append(task)

        completed = 0
        failed = 0

        for batch_idx in sorted(batches.keys()):
            batch_tasks = batches[batch_idx]
            batch_dir = self.output_dir / f"batch_{batch_idx:03d}"

            # 创建 Pipeline (指向 batch 子目录)
            pipeline = SimplifiedPipeline(str(batch_dir))

            # 使用信号量限制并发
            semaphore = asyncio.Semaphore(self.max_workers)

            async def run_single_task(task: TaskDefinition) -> TaskResult:
                async with semaphore:
                    return await self._execute_task(pipeline, task, batch_dir)

            # 并发执行
            results = await asyncio.gather(
                *[run_single_task(task) for task in batch_tasks],
                return_exceptions=True
            )

            # 统计
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    task_result = TaskResult(
                        task_id=batch_tasks[i].task_id,
                        status='failed',
                        error=str(result),
                        retry_count=self.max_retries
                    )
                    self.progress.mark_result(task_result)
                    failed += 1
                elif result.status == 'completed':
                    completed += 1
                else:
                    failed += 1

        logger.info(f"完成: {completed} 成功, {failed} 失败")

    async def _execute_task(
        self,
        pipeline: 'SimplifiedPipeline',
        task: TaskDefinition,
        batch_dir: Path
    ) -> TaskResult:
        """执行单个任务（带重试）+ 生成摘要"""
        start_time = datetime.now()
        last_error = None

        for retry in range(self.max_retries):
            try:
                result = await pipeline.run_async(task)
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                if result.get('status') == 'completed':
                    # 异步入队 Summary（非阻塞）
                    if self.generate_summary and result.get('output_dir'):
                        await self._enqueue_summary(
                            chart_dir=Path(result.get('output_dir')),
                            task=task
                        )

                    task_result = TaskResult(
                        task_id=task.task_id,
                        status='completed',
                        chart_id=result.get('chart_id'),
                        output_dir=result.get('output_dir'),
                        duration_ms=duration_ms,
                        retry_count=retry,
                        summary_generated=False  # 异步生成
                    )
                    self.progress.mark_result(task_result)

                    queue_size = self._summary_queue.qsize() if self._summary_queue else 0
                    logger.info(f"✓ {task.task_id}: {task.chart_type}/{task.theme}/{task.data_source} [📝队列:{queue_size}]")
                    return task_result
                else:
                    last_error = result.get('error', 'Unknown error')
                    logger.warning(f"✗ {task.task_id} 尝试 {retry+1}/{self.max_retries}: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"✗ {task.task_id} 尝试 {retry+1}/{self.max_retries}: {e}")

        # 所有重试都失败
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        task_result = TaskResult(
            task_id=task.task_id,
            status='failed',
            error=last_error,
            duration_ms=duration_ms,
            retry_count=self.max_retries
        )
        self.progress.mark_result(task_result)
        logger.error(f"✗✗ {task.task_id} 最终失败: {last_error}")
        return task_result

    # =========================================================================
    # Summary 异步并行处理
    # =========================================================================

    async def _generate_summary_for_chart(
        self,
        chart_dir: Path,
        task: TaskDefinition
    ) -> bool:
        """为单张图片生成摘要"""
        try:
            # 延迟导入，避免循环依赖
            import sys
            scripts_dir = Path(__file__).parent.parent.parent.parent / "scripts"
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))

            from generate_summary import process_single_chart

            # 使用锁保护计数器
            async with self._summary_lock:
                self._summary_counter += 1
                index = self._summary_counter

            # 在线程池中执行
            loop = asyncio.get_event_loop()
            summary_result = await loop.run_in_executor(
                None,
                process_single_chart,
                chart_dir,
                self.summary_output_dir,
                index,
                self.total_tasks,
                "gemini-3-pro-preview"
            )

            if summary_result.success:
                logger.debug(f"📝 {task.task_id} 摘要生成完成")
                return True
            else:
                logger.warning(f"⚠️ {task.task_id} 摘要生成失败: {summary_result.error}")
                return False

        except ImportError as e:
            logger.warning(f"⚠️ 无法导入摘要生成模块: {e}")
            return False
        except Exception as e:
            logger.warning(f"⚠️ {task.task_id} 摘要生成异常: {e}")
            return False

    async def _start_summary_workers(self):
        """启动 Summary 后台 workers"""
        if not self.generate_summary:
            return

        self._summary_queue = asyncio.Queue()

        for i in range(self._summary_worker_count):
            worker = asyncio.create_task(self._summary_worker(i))
            self._summary_workers.append(worker)

        logger.info(f"🚀 启动 {self._summary_worker_count} 个 Summary workers")

    async def _summary_worker(self, worker_id: int):
        """Summary worker 主循环"""
        while True:
            try:
                item = await self._summary_queue.get()

                if item is None:  # 停止信号
                    self._summary_queue.task_done()
                    break

                chart_dir, task = item
                await self._generate_summary_for_chart(chart_dir, task)
                self._summary_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Summary worker {worker_id} 异常: {e}")
                self._summary_queue.task_done()

    async def _enqueue_summary(self, chart_dir: Path, task: TaskDefinition):
        """将 summary 任务加入队列"""
        if self._summary_queue is not None:
            await self._summary_queue.put((chart_dir, task))

    async def _wait_summary_completion(self):
        """等待所有 summary 任务完成"""
        if not self.generate_summary or self._summary_queue is None:
            return

        logger.info(f"⏳ 等待 {self._summary_queue.qsize()} 个 Summary 任务完成...")
        await self._summary_queue.join()

        # 发送停止信号
        for _ in range(self._summary_worker_count):
            await self._summary_queue.put(None)

        # 等待 workers 退出
        await asyncio.gather(*self._summary_workers, return_exceptions=True)
        logger.info("✅ 所有 Summary 任务已完成")
