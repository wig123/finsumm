#!/usr/bin/env python
"""程序化批量生成脚本 v2 - 薄入口

特点：
- 程序化数据选择（替代 Planner LLM）
- 使用 coder_user_template_v2.md 生成 question + labels + code
- 数据选择 100% 正确，不会出现数据源不匹配
- 执行速度更快（省去 Planner LLM 调用）

用法:
    # 生成任务清单（使用 v2 配置）
    python scripts/run_programmatic.py generate --total 1000 --output programmatic_1000

    # 预览任务分布
    python scripts/run_programmatic.py preview --dir programmatic_1000

    # 执行生成
    python scripts/run_programmatic.py run --dir programmatic_1000

    # 查看进度
    python scripts/run_programmatic.py status --dir programmatic_1000

    # 重试失败任务
    python scripts/run_programmatic.py retry --dir programmatic_1000
"""

import sys
import argparse
import asyncio
import logging
from pathlib import Path
from collections import defaultdict
from typing import List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 从 capabilities_v2 导入
from src.capabilities_v2 import (
    TaskDefinitionV2,
    TaskGeneratorV2,
    ManifestManagerV2,
    ProgressManager,
    TaskExecutorV2,
)


# ============================================================================
# 统计打印
# ============================================================================

def print_task_statistics(tasks: List[TaskDefinitionV2]):
    """打印任务统计"""
    print("\n" + "="*60)
    print(f"任务统计: {len(tasks)} 个任务 (程序化模式)")
    print("="*60)

    # 语言分布
    lang_counts = defaultdict(int)
    for t in tasks:
        lang_counts[t.language] += 1

    print("\n语言分布:")
    for lang, count in sorted(lang_counts.items()):
        print(f"  {lang}: {count} ({count/len(tasks)*100:.1f}%)")

    # 数据源分布
    ds_counts = defaultdict(int)
    for t in tasks:
        ds_counts[t.data_source] += 1

    print("\n数据源分布:")
    for ds, count in sorted(ds_counts.items(), key=lambda x: -x[1]):
        print(f"  {ds}: {count} ({count/len(tasks)*100:.1f}%)")

    # 数据形态分布
    shape_counts = defaultdict(int)
    for t in tasks:
        shape_counts[t.shape] += 1

    print("\n数据形态分布:")
    for shape, count in sorted(shape_counts.items(), key=lambda x: -x[1]):
        print(f"  {shape}: {count} ({count/len(tasks)*100:.1f}%)")

    # 图表类型分布 (Top 10)
    chart_counts = defaultdict(int)
    for t in tasks:
        chart_counts[t.chart_type] += 1

    print("\n图表类型 (Top 10):")
    for chart, count in sorted(chart_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {chart}: {count} ({count/len(tasks)*100:.1f}%)")

    # 主题分布 (Top 10)
    theme_counts = defaultdict(int)
    for t in tasks:
        theme_counts[t.theme] += 1

    print("\n主题分布 (Top 10):")
    for theme, count in sorted(theme_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {theme}: {count} ({count/len(tasks)*100:.1f}%)")

    # 视觉风格分布
    style_counts = defaultdict(int)
    for t in tasks:
        style_counts[t.visual_style] += 1

    print("\n视觉风格:")
    for style, count in sorted(style_counts.items(), key=lambda x: -x[1]):
        print(f"  {style}: {count} ({count/len(tasks)*100:.1f}%)")

    # 指标多样性
    unique_indicators = set(t.indicator for t in tasks)
    print(f"\n指标多样性: {len(unique_indicators)} 种不同指标")

    # 批次数
    max_batch = max(t.batch_index for t in tasks)
    print(f"\n批次数: {max_batch}")
    print("="*60)


# ============================================================================
# 命令处理
# ============================================================================

def cmd_generate(args):
    """生成任务清单"""
    generator = TaskGeneratorV2()
    tasks = generator.generate(total=args.total, batch_size=args.batch_size)

    # 打印统计
    print_task_statistics(tasks)

    # 保存清单
    output_dir = Path(args.output)
    manager = ManifestManagerV2(output_dir)

    if manager.exists() and not args.force:
        logger.error(f"目录已存在: {output_dir}，使用 --force 覆盖")
        return

    config = {
        'total': args.total,
        'batch_size': args.batch_size,
        'mode': 'programmatic_v2'
    }
    manager.save(tasks, config)


def cmd_preview(args):
    """预览任务分布"""
    output_dir = Path(args.dir)
    manager = ManifestManagerV2(output_dir)

    if not manager.exists():
        logger.error(f"任务清单不存在: {output_dir}")
        return

    tasks, config = manager.load()
    print_task_statistics(tasks)

    # 显示前 5 个任务示例
    print("\n前 5 个任务示例:")
    print("-"*60)
    for task in tasks[:5]:
        print(f"  {task.task_id}: {task.chart_type} / {task.theme}")
        print(f"    indicator: {task.indicator}")
        print(f"    data_source: {task.data_source}")
        print(f"    description: {task.indicator_description_zh}")
        print()


def cmd_run(args):
    """执行任务"""
    output_dir = Path(args.dir)
    manager = ManifestManagerV2(output_dir)

    if not manager.exists():
        logger.error(f"任务清单不存在: {output_dir}")
        return

    tasks, config = manager.load()

    # 创建执行器
    executor = TaskExecutorV2(
        output_dir=output_dir,
        batch_size=config.get('batch_size', 200),
        max_workers=args.max_workers,
        max_retries=args.retries,
        generate_summary=not args.no_summary,
        total_tasks=len(tasks)
    )

    # 执行任务
    asyncio.run(executor.run_all(tasks, retry_failed=False))


def cmd_retry(args):
    """重试失败任务"""
    output_dir = Path(args.dir)
    manager = ManifestManagerV2(output_dir)

    if not manager.exists():
        logger.error(f"任务清单不存在: {output_dir}")
        return

    tasks, config = manager.load()

    executor = TaskExecutorV2(
        output_dir=output_dir,
        batch_size=config.get('batch_size', 200),
        max_workers=args.max_workers,
        max_retries=args.retries,
        generate_summary=not args.no_summary,
        total_tasks=len(tasks)
    )

    asyncio.run(executor.run_all(tasks, retry_failed=True))


def cmd_status(args):
    """查看状态"""
    output_dir = Path(args.dir)
    manifest = ManifestManagerV2(output_dir)

    if not manifest.exists():
        logger.error(f"任务清单不存在: {output_dir}")
        return

    tasks, config = manifest.load()
    progress = ProgressManager(output_dir)
    stats = progress.get_stats()

    total = len(tasks)
    completed = stats['completed']
    failed = stats['failed']
    pending = total - completed - failed

    # 按数据源统计
    by_source = defaultdict(lambda: {'total': 0, 'completed': 0, 'failed': 0})
    for task in tasks:
        by_source[task.data_source]['total'] += 1
        if task.task_id in progress.completed_ids:
            by_source[task.data_source]['completed'] += 1
        elif task.task_id in progress.failed_ids:
            by_source[task.data_source]['failed'] += 1

    print(f"\n{'='*60}")
    print(f"进度统计: {output_dir.name}")
    print(f"{'='*60}")
    print(f"总任务数: {total}")
    print(f"已完成:   {completed} ({completed/total*100:.1f}%)")
    print(f"失败:     {failed} ({failed/total*100:.1f}%)")
    print(f"待执行:   {pending} ({pending/total*100:.1f}%)")

    print(f"\n按数据源:")
    for source, counts in sorted(by_source.items()):
        source_pending = counts['total'] - counts['completed'] - counts['failed']
        print(f"  {source}: {counts['completed']}/{counts['total']} 完成, {counts['failed']} 失败, {source_pending} 待执行")

    print(f"{'='*60}")

    # 进度条
    bar_width = 50
    completed_width = int(bar_width * completed / total) if total > 0 else 0
    failed_width = int(bar_width * failed / total) if total > 0 else 0
    pending_width = bar_width - completed_width - failed_width

    bar = '█' * completed_width + '▓' * failed_width + '░' * pending_width
    pct = completed/total*100 if total > 0 else 0
    print(f"\n[{bar}] {pct:.1f}%")
    print(f"{'='*60}\n")


# ============================================================================
# 主函数
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="程序化批量生成脚本 v2",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # generate 子命令
    gen_parser = subparsers.add_parser('generate', help='生成任务清单')
    gen_parser.add_argument('--total', type=int, default=1000, help='总任务数')
    gen_parser.add_argument('--batch-size', type=int, default=200, help='批次大小')
    gen_parser.add_argument('--output', '-o', required=True, help='输出目录')
    gen_parser.add_argument('--force', '-f', action='store_true', help='强制覆盖')

    # preview 子命令
    preview_parser = subparsers.add_parser('preview', help='预览任务分布')
    preview_parser.add_argument('--dir', '-d', required=True, help='任务目录')

    # run 子命令
    run_parser = subparsers.add_parser('run', help='执行任务')
    run_parser.add_argument('--dir', '-d', required=True, help='任务目录')
    run_parser.add_argument('--max-workers', type=int, default=5, help='最大并发数')
    run_parser.add_argument('--retries', type=int, default=3, help='最大重试次数')
    run_parser.add_argument('--no-summary', action='store_true', help='不生成摘要')

    # retry 子命令
    retry_parser = subparsers.add_parser('retry', help='重试失败任务')
    retry_parser.add_argument('--dir', '-d', required=True, help='任务目录')
    retry_parser.add_argument('--max-workers', type=int, default=5, help='最大并发数')
    retry_parser.add_argument('--retries', type=int, default=3, help='最大重试次数')
    retry_parser.add_argument('--no-summary', action='store_true', help='不生成摘要')

    # status 子命令
    status_parser = subparsers.add_parser('status', help='查看状态')
    status_parser.add_argument('--dir', '-d', required=True, help='任务目录')

    args = parser.parse_args()

    if args.command == 'generate':
        cmd_generate(args)
    elif args.command == 'preview':
        cmd_preview(args)
    elif args.command == 'run':
        cmd_run(args)
    elif args.command == 'retry':
        cmd_retry(args)
    elif args.command == 'status':
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
