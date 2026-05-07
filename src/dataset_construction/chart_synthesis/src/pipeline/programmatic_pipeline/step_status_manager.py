"""分步状态管理器 - 追踪每个步骤的执行状态"""

import json
import logging
import fcntl
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class StepName(str, Enum):
    """步骤名称"""
    FETCH = "fetch"
    RENDER = "render"
    SUMMARIZE = "summarize"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    DATA_READY = "data_ready"
    RENDERED = "rendered"
    COMPLETE = "complete"
    FETCH_FAILED = "fetch_failed"
    RENDER_FAILED = "render_failed"
    SUMMARY_FAILED = "summary_failed"


@dataclass
class StepResult:
    """单步执行结果"""
    task_id: str
    step: str
    status: str  # success / failed
    duration_seconds: float
    error: Optional[str] = None
    error_type: Optional[str] = None
    timestamp: Optional[str] = None
    output_dir: Optional[str] = None  # 任务输出目录路径

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class StepStatusManager:
    """分步状态管理器

    为每个步骤维护独立的 JSONL 状态文件，支持：
    - 原子写入（文件锁）
    - 增量追加
    - 状态查询
    - 失败任务过滤
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.status_dir = self.output_dir / "status"
        self.logs_dir = self.output_dir / "logs"

        # 创建目录
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # 状态文件路径
        self._status_files = {
            StepName.FETCH: self.status_dir / "step2_fetch.jsonl",
            StepName.RENDER: self.status_dir / "step3_render.jsonl",
            StepName.SUMMARIZE: self.status_dir / "step4_summarize.jsonl",
        }

        # 内存缓存
        self._cache: Dict[StepName, Dict[str, StepResult]] = {
            step: {} for step in StepName
        }
        self._cache_loaded = {step: False for step in StepName}

    def _load_cache(self, step: StepName):
        """加载步骤状态到缓存"""
        if self._cache_loaded[step]:
            return

        status_file = self._status_files[step]
        if status_file.exists():
            with open(status_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            result = StepResult(**data)
                            self._cache[step][result.task_id] = result
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.warning(f"解析状态行失败: {e}")

        self._cache_loaded[step] = True
        logger.debug(f"已加载 {step.value} 状态: {len(self._cache[step])} 条记录")

    def record_result(self, result: StepResult):
        """记录步骤执行结果（原子写入）"""
        step = StepName(result.step)
        status_file = self._status_files[step]

        # 原子追加写入
        with open(status_file, "a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # 更新缓存
        self._cache[step][result.task_id] = result

    def get_status(self, step: StepName, task_id: str) -> Optional[StepResult]:
        """获取任务在指定步骤的状态"""
        self._load_cache(step)
        return self._cache[step].get(task_id)

    def is_step_completed(self, step: StepName, task_id: str) -> bool:
        """检查任务是否完成指定步骤"""
        result = self.get_status(step, task_id)
        return result is not None and result.status == "success"

    def is_step_failed(self, step: StepName, task_id: str) -> bool:
        """检查任务在指定步骤是否失败"""
        result = self.get_status(step, task_id)
        return result is not None and result.status == "failed"

    def get_pending_tasks(self, step: StepName, all_task_ids: List[str]) -> List[str]:
        """获取指定步骤的待执行任务"""
        self._load_cache(step)
        completed = set(
            tid for tid, result in self._cache[step].items()
            if result.status == "success"
        )
        return [tid for tid in all_task_ids if tid not in completed]

    def get_failed_tasks(self, step: StepName, all_task_ids: List[str]) -> List[str]:
        """获取指定步骤的失败任务"""
        self._load_cache(step)
        failed = set(
            tid for tid, result in self._cache[step].items()
            if result.status == "failed"
        )
        return [tid for tid in all_task_ids if tid in failed]

    def get_step_statistics(self, step: StepName) -> Dict:
        """获取步骤统计信息"""
        self._load_cache(step)

        total = len(self._cache[step])
        success = sum(1 for r in self._cache[step].values() if r.status == "success")
        failed = sum(1 for r in self._cache[step].values() if r.status == "failed")

        # 错误类型统计
        error_types = {}
        for result in self._cache[step].values():
            if result.error_type:
                error_types[result.error_type] = error_types.get(result.error_type, 0) + 1

        # 平均耗时
        durations = [r.duration_seconds for r in self._cache[step].values() if r.duration_seconds > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "step": step.value,
            "total_processed": total,
            "success": success,
            "failed": failed,
            "success_rate": f"{success/total*100:.1f}%" if total > 0 else "N/A",
            "avg_duration_seconds": round(avg_duration, 2),
            "error_types": error_types
        }

    def get_task_overall_status(self, task_id: str) -> TaskStatus:
        """获取任务的整体状态"""
        # 检查各步骤状态
        fetch_result = self.get_status(StepName.FETCH, task_id)
        render_result = self.get_status(StepName.RENDER, task_id)
        summary_result = self.get_status(StepName.SUMMARIZE, task_id)

        # 判断状态
        if summary_result and summary_result.status == "success":
            return TaskStatus.COMPLETE
        if summary_result and summary_result.status == "failed":
            return TaskStatus.SUMMARY_FAILED

        if render_result and render_result.status == "success":
            return TaskStatus.RENDERED
        if render_result and render_result.status == "failed":
            return TaskStatus.RENDER_FAILED

        if fetch_result and fetch_result.status == "success":
            return TaskStatus.DATA_READY
        if fetch_result and fetch_result.status == "failed":
            return TaskStatus.FETCH_FAILED

        return TaskStatus.PENDING

    def get_task_output_dir(self, task_id: str) -> Optional[str]:
        """获取任务的输出目录 (从 FETCH 步骤记录中读取)"""
        fetch_result = self.get_status(StepName.FETCH, task_id)
        if fetch_result and fetch_result.output_dir:
            return fetch_result.output_dir
        return None

    def get_overall_statistics(self, total_tasks: int) -> Dict:
        """获取整体统计"""
        stats = {
            "total_tasks": total_tasks,
            "steps": {}
        }

        for step in StepName:
            stats["steps"][step.value] = self.get_step_statistics(step)

        # 计算各状态的任务数（基于最终状态）
        # 这需要遍历所有任务，但如果任务列表很大，可以优化
        return stats
