"""清单管理器 v2"""

import json
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from typing import List, Dict, Tuple

from ..models import TaskDefinition

logger = logging.getLogger(__name__)


class ManifestManager:
    """管理任务清单 v2"""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.manifest_file = self.output_dir / "manifest.json"

    def save(self, tasks: List[TaskDefinition], config: Dict):
        """保存任务清单"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            'version': '2.0-programmatic',
            'created_at': datetime.now().isoformat(),
            'total_tasks': len(tasks),
            'config': config,
            'tasks': [asdict(task) for task in tasks]
        }

        with open(self.manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.info(f"任务清单已保存: {self.manifest_file}")

    def load(self) -> Tuple[List[TaskDefinition], Dict]:
        """加载任务清单"""
        if not self.manifest_file.exists():
            raise FileNotFoundError(f"任务清单不存在: {self.manifest_file}")

        with open(self.manifest_file, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        tasks = [TaskDefinition(**t) for t in manifest['tasks']]
        config = manifest.get('config', {})

        logger.info(f"已加载 {len(tasks)} 个任务")
        return tasks, config

    def exists(self) -> bool:
        return self.manifest_file.exists()
