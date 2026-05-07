"""进度管理器 - 支持中断续跑"""

import json
import fcntl
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from typing import Set, Dict

from ..models import TaskResult

logger = logging.getLogger(__name__)


class ProgressManager:
    """管理进度，支持中断续跑"""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.progress_file = self.output_dir / "progress.jsonl"
        self.completed_ids: Set[str] = set()
        self.failed_ids: Set[str] = set()
        self._load_progress()

    def _load_progress(self):
        """从进度文件加载已完成/失败的任务"""
        if not self.progress_file.exists():
            return

        with open(self.progress_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    task_id = record.get('task_id')
                    status = record.get('status')
                    if status == 'completed':
                        self.completed_ids.add(task_id)
                        self.failed_ids.discard(task_id)
                    elif status == 'failed':
                        self.failed_ids.add(task_id)
                except json.JSONDecodeError:
                    continue

        logger.info(f"从进度文件加载: {len(self.completed_ids)} 已完成, {len(self.failed_ids)} 失败")

    def is_completed(self, task_id: str) -> bool:
        return task_id in self.completed_ids

    def is_failed(self, task_id: str) -> bool:
        return task_id in self.failed_ids

    def mark_result(self, result: TaskResult):
        """标记任务结果并追加到进度文件"""
        record = asdict(result)
        record['timestamp'] = datetime.now().isoformat()

        # 使用文件锁保证并发安全
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # 更新内存中的状态
        if result.status == 'completed':
            self.completed_ids.add(result.task_id)
            self.failed_ids.discard(result.task_id)
        elif result.status == 'failed':
            self.failed_ids.add(result.task_id)

    def get_stats(self) -> Dict[str, int]:
        return {
            'completed': len(self.completed_ids),
            'failed': len(self.failed_ids)
        }
