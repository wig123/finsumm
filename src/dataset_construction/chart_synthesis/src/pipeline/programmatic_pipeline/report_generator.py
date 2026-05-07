"""分步报告生成器 - 生成每个步骤的详细报告"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from .step_status_manager import StepStatusManager, StepName, StepResult
from ..models import TaskDefinition

logger = logging.getLogger(__name__)


class ReportGenerator:
    """分步报告生成器

    为每个步骤生成详细的 JSON 报告，包含：
    - 执行统计（成功率、耗时）
    - 分类统计（按数据源、主题、图表类型等）
    - 错误汇总
    - 失败任务列表
    """

    def __init__(self, output_dir: Path, status_manager: StepStatusManager):
        self.output_dir = Path(output_dir)
        self.reports_dir = self.output_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.status_manager = status_manager

    def generate_step_report(
        self,
        step: StepName,
        tasks: List[TaskDefinition],
        start_time: datetime,
        end_time: datetime
    ) -> Dict:
        """生成单步报告"""
        duration = (end_time - start_time).total_seconds()

        # 基础统计
        task_map = {t.task_id: t for t in tasks}
        stats = self.status_manager.get_step_statistics(step)

        # 按维度分类统计
        by_data_source = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
        by_theme = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
        by_chart_type = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})

        failed_tasks = []

        for task in tasks:
            result = self.status_manager.get_status(step, task.task_id)
            if result is None:
                continue

            # 数据源统计
            by_data_source[task.data_source]["total"] += 1
            if result.status == "success":
                by_data_source[task.data_source]["success"] += 1
            else:
                by_data_source[task.data_source]["failed"] += 1

            # 主题统计
            by_theme[task.theme]["total"] += 1
            if result.status == "success":
                by_theme[task.theme]["success"] += 1
            else:
                by_theme[task.theme]["failed"] += 1

            # 图表类型统计
            by_chart_type[task.chart_type]["total"] += 1
            if result.status == "success":
                by_chart_type[task.chart_type]["success"] += 1
            else:
                by_chart_type[task.chart_type]["failed"] += 1

            # 收集失败任务
            if result.status == "failed":
                failed_tasks.append({
                    "task_id": task.task_id,
                    "indicator": task.indicator,
                    "data_source": task.data_source,
                    "theme": task.theme,
                    "chart_type": task.chart_type,
                    "error_type": result.error_type,
                    "error": result.error[:500] if result.error else None  # 截断长错误
                })

        report = {
            "step": step.value,
            "timestamp": end_time.isoformat(),
            "duration_seconds": round(duration, 2),
            "total": len(tasks),
            "processed": stats["total_processed"],
            "success": stats["success"],
            "failed": stats["failed"],
            "success_rate": stats["success_rate"],
            "avg_task_duration": stats["avg_duration_seconds"],
            "by_data_source": dict(by_data_source),
            "by_theme": dict(by_theme),
            "by_chart_type": dict(by_chart_type),
            "error_summary": stats["error_types"],
            "failed_tasks": failed_tasks[:100]  # 最多记录100个失败任务
        }

        # 保存报告
        report_file = self.reports_dir / f"step{self._step_number(step)}_{step.value}_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"报告已保存: {report_file}")
        return report

    def _step_number(self, step: StepName) -> int:
        """获取步骤编号"""
        return {
            StepName.FETCH: 2,
            StepName.RENDER: 3,
            StepName.SUMMARIZE: 4
        }[step]

    def generate_config_report(self, tasks: List[TaskDefinition]) -> Dict:
        """生成配置验证报告 (Step 1)"""
        # 统计分布
        distributions = {
            "language": defaultdict(int),
            "data_source": defaultdict(int),
            "shape": defaultdict(int),
            "theme": defaultdict(int),
            "chart_type": defaultdict(int),
            "visual_style": defaultdict(int),
        }

        for task in tasks:
            distributions["language"][task.language] += 1
            distributions["data_source"][task.data_source] += 1
            distributions["shape"][task.shape] += 1
            distributions["theme"][task.theme] += 1
            distributions["chart_type"][task.chart_type] += 1
            distributions["visual_style"][task.visual_style] += 1

        # 计算指标多样性
        unique_indicators = set(t.indicator for t in tasks)

        # 验证检查
        validations = []

        # 检查1: 图表-主题组合是否合理
        chart_theme_combos = defaultdict(set)
        for task in tasks:
            chart_theme_combos[task.chart_type].add(task.theme)

        # 检查2: 数据源覆盖率
        data_sources_used = set(t.data_source for t in tasks)
        expected_sources = {"FRED", "yfinance", "baostock", "Synthetic"}
        missing_sources = expected_sources - data_sources_used
        if missing_sources:
            validations.append({
                "type": "warning",
                "message": f"未使用的数据源: {missing_sources}"
            })

        # 检查3: 时序 vs 横截面比例
        ts_count = sum(1 for t in tasks if t.shape.startswith("TS_") or t.shape == "OHLC")
        cs_count = sum(1 for t in tasks if t.shape.startswith("CS_") or t.shape == "MATRIX")
        ts_ratio = ts_count / len(tasks) if tasks else 0

        if ts_ratio < 0.6:
            validations.append({
                "type": "warning",
                "message": f"时序数据占比偏低: {ts_ratio:.1%}，建议 >= 60%"
            })

        report = {
            "step": "config",
            "timestamp": datetime.now().isoformat(),
            "total_tasks": len(tasks),
            "unique_indicators": len(unique_indicators),
            "distributions": {k: dict(v) for k, v in distributions.items()},
            "time_series_ratio": f"{ts_ratio:.1%}",
            "validations": validations,
            "status": "valid" if not any(v["type"] == "error" for v in validations) else "invalid"
        }

        # 保存报告
        report_file = self.reports_dir / "step1_config_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"配置报告已保存: {report_file}")
        return report

    def generate_overall_report(self, tasks: List[TaskDefinition]) -> Dict:
        """生成整体报告"""
        task_statuses = defaultdict(int)

        for task in tasks:
            status = self.status_manager.get_task_overall_status(task.task_id)
            task_statuses[status.value] += 1

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_tasks": len(tasks),
            "task_statuses": dict(task_statuses),
            "completion_rate": f"{task_statuses.get('complete', 0) / len(tasks) * 100:.1f}%" if tasks else "N/A",
            "steps": {}
        }

        for step in StepName:
            report["steps"][step.value] = self.status_manager.get_step_statistics(step)

        # 保存报告
        report_file = self.reports_dir / "overall_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"整体报告已保存: {report_file}")
        return report

    def print_step_summary(self, step: StepName, report: Dict):
        """打印步骤摘要到控制台"""
        print(f"\n{'='*60}")
        print(f"Step {self._step_number(step)}: {step.value.upper()} 完成")
        print(f"{'='*60}")
        print(f"总任务: {report['total']}")
        print(f"已处理: {report['processed']}")
        print(f"成功: {report['success']} ({report['success_rate']})")
        print(f"失败: {report['failed']}")
        print(f"总耗时: {report['duration_seconds']:.1f}s")
        print(f"平均耗时: {report['avg_task_duration']:.2f}s/任务")

        if report.get("error_summary"):
            print(f"\n错误类型分布:")
            for err_type, count in sorted(report["error_summary"].items(), key=lambda x: -x[1])[:5]:
                print(f"  {err_type}: {count}")

        print(f"\n详细报告: {self.reports_dir / f'step{self._step_number(step)}_{step.value}_report.json'}")
        print("="*60)
