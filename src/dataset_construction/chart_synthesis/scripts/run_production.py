#!/usr/bin/env python
"""生产级批量生成脚本

支持：
- 根据配额约束自动生成任务
- 高并发执行：FRED/yfinance/baostock/efinance/Synthetic 5并发
- 失败重试
- 实时存储结果
- 中断续跑
- 分批嵌套目录
- 实时生成图片摘要

用法:
    # 生成任务清单
    python scripts/run_production.py generate --total 4000 --output production_4000

    # 预览任务分布
    python scripts/run_production.py preview --dir production_4000

    # 执行生成（支持中断续跑，默认生成摘要）
    python scripts/run_production.py run --dir production_4000

    # 执行生成（不生成摘要）
    python scripts/run_production.py run --dir production_4000 --no-summary

    # 查看进度
    python scripts/run_production.py status --dir production_4000

    # 重试失败任务
    python scripts/run_production.py retry --dir production_4000

    # 生成最终报告
    python scripts/run_production.py report --dir production_4000
"""

import sys
import json
import yaml
import argparse
import logging
import asyncio
import random
import fcntl
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Set, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, asdict

# 添加项目根目录和 scripts 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from src.models.planner_models import PlannerInput
from src.capabilities.pipeline_orchestration import ChartSynthesisPipeline

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 数据类
# ============================================================================

@dataclass
class TaskDefinition:
    """任务定义"""
    task_id: str
    chart_type: str
    language: str
    theme: str
    visual_style: str
    batch_index: int
    data_source: str = "FRED"  # FRED, yfinance, baostock, efinance, Synthetic
    is_frontend: bool = False
    
    def to_planner_input(self) -> PlannerInput:
        return PlannerInput(
            chart_type=self.chart_type,
            language=self.language,
            theme=self.theme,
            visual_style=self.visual_style,
            is_frontend=self.is_frontend
        )


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    status: str  # completed, failed
    chart_id: Optional[str] = None
    output_dir: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    retry_count: int = 0
    timestamp: str = ""
    summary_generated: bool = False


# ============================================================================
# 配额加载器
# ============================================================================

class QuotaLoader:
    """加载配额配置"""
    
    def __init__(self, config_dir: Path = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        
        self.config_dir = config_dir
        self.constraints = self._load_yaml("generation_constraints.yaml")
        self.chart_mapping = self._load_yaml("chart_library_mapping.yaml")
        self.theme_mapping = self._load_yaml("theme_mapping.yaml")
    
    def _load_yaml(self, filename: str) -> Dict:
        filepath = self.config_dir / filename
        if not filepath.exists():
            logger.warning(f"配置文件不存在: {filepath}")
            return {}
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def get_language_quota(self) -> Dict[str, float]:
        return self.constraints.get('language_quota', {'zh-CN': 0.5, 'en-US': 0.5})
    
    def get_visual_style_quota(self) -> Dict[str, float]:
        return self.constraints.get('visual_style_quota', {'default': 1.0})
    
    def get_chart_types_by_tier(self) -> Dict[int, List[Tuple[str, float]]]:
        """返回按 tier 分组的图表类型及其权重"""
        chart_types = self.chart_mapping.get('chart_types', {})
        by_tier = defaultdict(list)
        for chart_type, config in chart_types.items():
            tier = config.get('tier', 1)
            weight = config.get('weight', 0.01)
            by_tier[tier].append((chart_type, weight))
        return dict(by_tier)
    
    def get_theme_weights(self) -> Dict[str, float]:
        """返回主题权重"""
        themes = self.theme_mapping.get('themes', {})
        return {name: config.get('weight', 0.05) for name, config in themes.items()}
    
    def get_theme_data_sources(self) -> Dict[str, List[str]]:
        """返回每个主题的典型数据源"""
        themes = self.theme_mapping.get('themes', {})
        return {name: config.get('typical_data_sources', ['FRED']) 
                for name, config in themes.items()}
    
    def get_chart_theme_affinity(self) -> Dict[str, Dict[str, float]]:
        return self.constraints.get('chart_theme_affinity', {})
    
    def get_style_theme_affinity(self) -> Dict[str, Dict[str, float]]:
        return self.constraints.get('style_theme_affinity', {})
    
    def get_hard_constraints(self) -> Dict:
        return self.constraints.get('hard_constraints', {})


# ============================================================================
# 任务生成器
# ============================================================================

class TaskGenerator:
    """根据配额约束生成任务"""
    
    # 需要合成数据的主题（数据源非常有限）
    SYNTHETIC_THEMES = [
        'insurance', 'esg_sustainable', 'ma_ipos',  # 核心合成主题
        'banking_credit', 'real_estate', 'asset_management'  # 使用合成数据的主题
    ]
    
    # 部分合成数据主题（50%概率使用合成）
    PARTIAL_SYNTHETIC_THEMES = [
        'corporate_finance', 'accounting_reporting', 'payments_fintech'
    ]
    PARTIAL_SYNTHETIC_RATIO = 0.5
    
    # 需要合成数据的图表类型（仅特殊结构）
    SYNTHETIC_CHARTS = ['treemap', 'sankey']  # 移除 heatmap/contour/radar，可用真实数据
    
    # FRED 偏好的主题（美国宏观数据，减少到~25%）
    FRED_THEMES = [
        'macro_policy', 'inflation', 'fiscal_policy', 'monetary_conditions'
    ]
    
    # Baostock 偏好的图表类型（A股指数 OHLCV，提高到~20%）
    BAOSTOCK_CHARTS = [
        'candlestick', 'candlestick_volume', 'ohlc', 'bollinger_bands',
        'ichimoku_cloud', 'renko', 'point_figure', 'volume_profile'
    ]
    
    # yfinance 偏好的主题/图表（全球/外汇，约15%）
    YFINANCE_THEMES = ['fx_trade']
    YFINANCE_CHARTS = ['candlestick', 'candlestick_volume', 'ohlc', 'bollinger_bands']
    
    # Efinance 已废弃（API不稳定），期货数据改用 yfinance
    # EFINANCE_THEMES = ['derivatives', 'commodities']  # 已移除
    # EFINANCE_CHARTS = ['candlestick', 'candlestick_volume', 'ohlc']  # 已移除
    
    def __init__(self, quota_loader: QuotaLoader = None):
        self.quota = quota_loader or QuotaLoader()
    
    def generate(self, total: int = 4000, batch_size: int = 200) -> List[TaskDefinition]:
        """生成任务列表"""
        logger.info(f"开始生成 {total} 个任务...")
        
        tasks = []
        
        # 1. 按语言分配
        lang_quota = self.quota.get_language_quota()
        lang_counts = {lang: int(total * ratio) for lang, ratio in lang_quota.items()}
        
        # 2. 获取图表类型权重
        chart_types_by_tier = self.quota.get_chart_types_by_tier()
        all_chart_weights = {}
        for tier, chart_list in chart_types_by_tier.items():
            for chart_type, weight in chart_list:
                all_chart_weights[chart_type] = weight
        
        # 归一化权重
        total_weight = sum(all_chart_weights.values())
        chart_probs = {k: v/total_weight for k, v in all_chart_weights.items()}
        
        # 3. 获取主题权重
        theme_weights = self.quota.get_theme_weights()
        total_theme_weight = sum(theme_weights.values())
        theme_probs = {k: v/total_theme_weight for k, v in theme_weights.items()}
        
        # 4. 获取视觉风格权重
        style_quota = self.quota.get_visual_style_quota()
        total_style_weight = sum(style_quota.values())
        style_probs = {k: v/total_style_weight for k, v in style_quota.items()}
        
        # 5. 获取亲和度矩阵
        chart_theme_affinity = self.quota.get_chart_theme_affinity()
        style_theme_affinity = self.quota.get_style_theme_affinity()
        hard_constraints = self.quota.get_hard_constraints()
        theme_data_sources = self.quota.get_theme_data_sources()
        
        # 6. 生成任务
        task_idx = 0
        for language, count in lang_counts.items():
            for _ in range(count):
                # 选择图表类型
                chart_type = self._weighted_choice(chart_probs)
                
                # 选择主题（考虑图表-主题亲和度）
                theme = self._select_theme_for_chart(
                    chart_type, theme_probs, chart_theme_affinity, hard_constraints
                )
                
                # 选择视觉风格（考虑风格-主题亲和度）
                visual_style = self._select_style_for_theme(
                    theme, chart_type, style_probs, style_theme_affinity, hard_constraints
                )
                
                # 推断数据源
                data_source = self._infer_data_source(theme, chart_type, theme_data_sources)
                
                # 计算 batch_index
                batch_index = task_idx // batch_size + 1
                
                # 生成任务ID
                task_id = f"task_{task_idx+1:05d}"
                
                task = TaskDefinition(
                    task_id=task_id,
                    chart_type=chart_type,
                    language=language,
                    theme=theme,
                    visual_style=visual_style,
                    batch_index=batch_index,
                    data_source=data_source
                )
                tasks.append(task)
                task_idx += 1
        
        # 打乱顺序（但保持 batch_index 正确）
        random.shuffle(tasks)
        for i, task in enumerate(tasks):
            task.batch_index = i // batch_size + 1
            task.task_id = f"task_{i+1:05d}"
        
        logger.info(f"成功生成 {len(tasks)} 个任务")
        return tasks
    
    def _infer_data_source(
        self, 
        theme: str, 
        chart_type: str,
        theme_data_sources: Dict[str, List[str]]
    ) -> str:
        """推断数据源
        
        目标分布（Efinance已废弃，改用yfinance）：
        - FRED: ~25% (美国宏观)
        - Baostock: ~25% (A股指数OHLC)
        - yfinance: ~30% (全球股指/外汇/商品OHLC)
        - Synthetic: ~20% (横截面/受限主题/特殊图表)
        """
        import random
        
        # 1. 合成数据（特定主题或图表类型）
        if theme in self.SYNTHETIC_THEMES:
            return "Synthetic"
        if chart_type in self.SYNTHETIC_CHARTS:
            return "Synthetic"
        
        # 1.5 部分合成主题（70% 概率使用合成）
        if theme in self.PARTIAL_SYNTHETIC_THEMES:
            if random.random() < self.PARTIAL_SYNTHETIC_RATIO:
                return "Synthetic"
            else:
                return "FRED"
        
        # 2. FRED 偏好主题（美国宏观数据）
        if theme in self.FRED_THEMES:
            return "FRED"
        
        # 3. 需要 OHLCV 数据的图表类型（K线图等）
        needs_ohlcv = chart_type in self.BAOSTOCK_CHARTS
        
        if needs_ohlcv:
            # 根据主题分配到不同的 OHLCV 数据源
            if theme == 'equity_markets':
                # A股/全球市场：Baostock 和 yfinance 均衡
                return random.choice(['Baostock', 'Baostock', 'yfinance', 'yfinance'])
            elif theme == 'fx_trade':
                # 外汇市场：使用 yfinance
                return "yfinance"
            elif theme in ['derivatives']:
                # 衍生品/期货：使用 yfinance（全球期货）
                return "yfinance"
            elif theme in ['commodities']:
                # 商品：使用 yfinance（GC=F, CL=F等）
                return "yfinance"
            elif theme == 'digital_assets':
                # 数字资产：yfinance（支持加密货币）
                return "yfinance"
            else:
                # 其他需要 OHLCV：Baostock 和 yfinance
                return random.choice(['Baostock', 'Baostock', 'yfinance', 'yfinance'])
        
        # 4. 非 OHLCV 图表类型
        if theme == 'fx_trade':
            return "yfinance"
        elif theme in ['derivatives']:
            return "Synthetic"  # 期权波动率等数据用合成
        elif theme in ['commodities']:
            # 商品单值数据：FRED 或合成
            return random.choice(['FRED', 'yfinance'])
        elif theme == 'growth_employment':
            # 增长就业：随机分配，增加合成比例
            return random.choice(['FRED', 'Synthetic'])
        elif theme == 'fixed_income':
            # 固定收益：随机分配
            return random.choice(['FRED', 'Synthetic'])
        
        # 5. 默认随机分配（均衡 Baostock/yfinance/Synthetic）
        return random.choice(['FRED', 'Baostock', 'Baostock', 'yfinance', 'yfinance', 'Synthetic'])
    
    def _weighted_choice(self, probs: Dict[str, float]) -> str:
        """加权随机选择"""
        items = list(probs.keys())
        weights = list(probs.values())
        return random.choices(items, weights=weights, k=1)[0]
    
    def _select_theme_for_chart(
        self, 
        chart_type: str, 
        theme_probs: Dict[str, float],
        chart_theme_affinity: Dict[str, Dict[str, float]],
        hard_constraints: Dict
    ) -> str:
        """为图表类型选择合适的主题"""
        # 获取图表类型的主题亲和度
        affinity = chart_theme_affinity.get(chart_type, {})
        default_affinity = affinity.get('default', 0.5)
        
        # 获取禁止的主题
        forbidden_themes = hard_constraints.get('chart_forbidden_themes', {}).get(chart_type, [])
        
        # 调整主题权重
        adjusted_probs = {}
        for theme, prob in theme_probs.items():
            if theme in forbidden_themes:
                continue  # 跳过禁止的主题
            theme_affinity = affinity.get(theme, default_affinity)
            adjusted_probs[theme] = prob * theme_affinity
        
        # 归一化
        total = sum(adjusted_probs.values())
        if total == 0:
            # 如果所有主题都被禁止，使用默认主题
            return list(theme_probs.keys())[0]
        
        adjusted_probs = {k: v/total for k, v in adjusted_probs.items()}
        return self._weighted_choice(adjusted_probs)
    
    def _select_style_for_theme(
        self,
        theme: str,
        chart_type: str,
        style_probs: Dict[str, float],
        style_theme_affinity: Dict[str, Dict[str, float]],
        hard_constraints: Dict
    ) -> str:
        """为主题选择合适的视觉风格"""
        # 获取禁止的风格
        forbidden_styles = []
        style_forbidden_themes = hard_constraints.get('style_forbidden_themes', {})
        for style, themes in style_forbidden_themes.items():
            if theme in themes:
                forbidden_styles.append(style)
        
        style_forbidden_charts = hard_constraints.get('style_forbidden_charts', {})
        for style, charts in style_forbidden_charts.items():
            if chart_type in charts:
                forbidden_styles.append(style)
        
        # 调整风格权重
        adjusted_probs = {}
        for style, prob in style_probs.items():
            if style in forbidden_styles:
                continue
            # 获取风格-主题亲和度
            affinity = style_theme_affinity.get(style, {})
            default_affinity = affinity.get('default', 0.5)
            theme_affinity = affinity.get(theme, default_affinity)
            adjusted_probs[style] = prob * theme_affinity
        
        # 归一化
        total = sum(adjusted_probs.values())
        if total == 0:
            return 'default'
        
        adjusted_probs = {k: v/total for k, v in adjusted_probs.items()}
        return self._weighted_choice(adjusted_probs)


# ============================================================================
# 进度管理器
# ============================================================================

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


# ============================================================================
# 批量执行器
# ============================================================================

class BatchExecutor:
    """分批执行，高并发"""
    
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
        self._summary_lock = asyncio.Lock()  # 保护计数器的锁
        
        # 🔥 Summary 异步队列（后台并行处理）
        self._summary_queue: asyncio.Queue = None  # 延迟初始化
        self._summary_workers: List[asyncio.Task] = []
        self._summary_worker_count = max_workers  # Summary workers 数量（与图表生成并发数一致）
        
        if self._summary_counter > 0:
            logger.info(f"从已有摘要恢复计数: {self._summary_counter}")
    
    def _get_max_summary_index(self) -> int:
        """从已有的 summaries 目录中获取最大索引"""
        if not self.summary_output_dir.exists():
            return 0
        
        max_index = 0
        import re
        pattern = re.compile(r'^(\d+)_')
        
        for item in self.summary_output_dir.iterdir():
            if item.is_dir():
                match = pattern.match(item.name)
                if match:
                    index = int(match.group(1))
                    if index > max_index:
                        max_index = index
        
        return max_index
    
    def run(self, tasks: List[TaskDefinition], retry_failed: bool = False):
        """执行任务（高并发）"""
        # 过滤已完成的任务
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
        
        # 执行所有任务
        asyncio.run(self._run_all_tasks(pending_tasks))
        
        # 打印总结
        stats = self.progress.get_stats()
        logger.info(f"\n{'='*60}")
        logger.info(f"全部执行完成")
        logger.info(f"总计: {stats['completed']} 已完成, {stats['failed']} 失败")
        logger.info(f"{'='*60}")
    
    async def _run_all_tasks(self, tasks: List[TaskDefinition]):
        """执行所有任务"""
        # 🔥 启动 Summary workers
        await self._start_summary_workers()
        
        try:
            await self._run_task_group(tasks, self.max_workers, "ALL")
        finally:
            # 🔥 等待所有 Summary 任务完成
            await self._wait_summary_completion()
    
    async def _run_task_group(
        self, 
        tasks: List[TaskDefinition], 
        max_workers: int,
        group_name: str
    ):
        """执行一组任务"""
        logger.info(f"[{group_name}] 开始执行 {len(tasks)} 个任务")
        
        # 按 batch 分组
        batches = defaultdict(list)
        for task in tasks:
            batches[task.batch_index].append(task)
        
        completed = 0
        failed = 0
        
        for batch_idx in sorted(batches.keys()):
            batch_tasks = batches[batch_idx]
            batch_dir = self.output_dir / f"batch_{batch_idx:03d}"
            
            # 创建 Pipeline
            pipeline = ChartSynthesisPipeline(
                output_dir=str(batch_dir)
            )
            
            # 使用信号量限制并发
            semaphore = asyncio.Semaphore(max_workers)
            
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
        
        logger.info(f"[{group_name}] 完成: {completed} 成功, {failed} 失败")
    
    async def _execute_task(
        self, 
        pipeline: ChartSynthesisPipeline, 
        task: TaskDefinition,
        batch_dir: Path
    ) -> TaskResult:
        """执行单个任务（带重试）+ 生成摘要"""
        start_time = datetime.now()
        last_error = None
        
        for retry in range(self.max_retries):
            try:
                planner_input = task.to_planner_input()
                result = await pipeline.run_async(planner_input)
                
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                if result.get('status') == 'completed':
                    # 🔥 异步入队 Summary（非阻塞）
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
                        summary_generated=False  # 异步生成，此时未完成
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
    
    async def _generate_summary_for_chart(
        self, 
        chart_dir: Path, 
        task: TaskDefinition
    ) -> bool:
        """为单张图片生成摘要（直接调用 process_single_chart）"""
        try:
            # 导入 process_single_chart
            from run_batch_summary import process_single_chart
            
            # 使用锁保护计数器，确保每个任务获得唯一索引
            async with self._summary_lock:
                self._summary_counter += 1
                index = self._summary_counter
            
            # 在线程池中执行（因为是同步函数）
            loop = asyncio.get_event_loop()
            summary_result = await loop.run_in_executor(
                None,
                process_single_chart,
                chart_dir,              # chart_dir: Path
                self.summary_output_dir,  # output_dir: Path
                index,                  # index: int
                self.total_tasks,       # total: int
                "gemini-3-pro-preview"  # model: str
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

    # =========================================================================
    # 🔥 Summary 异步并行处理
    # =========================================================================
    
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
                # 从队列获取任务（带超时）
                item = await self._summary_queue.get()
                
                if item is None:  # 停止信号
                    self._summary_queue.task_done()
                    break
                
                chart_dir, task = item
                
                # 执行 summary 生成
                await self._generate_summary_for_chart(chart_dir, task)
                
                self._summary_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Summary worker {worker_id} 异常: {e}")
                self._summary_queue.task_done()
    
    async def _enqueue_summary(self, chart_dir: Path, task: TaskDefinition):
        """将 summary 任务加入队列（非阻塞）"""
        if self._summary_queue is not None:
            await self._summary_queue.put((chart_dir, task))
    
    async def _wait_summary_completion(self):
        """等待所有 summary 任务完成"""
        if not self.generate_summary or self._summary_queue is None:
            return
        
        # 等待队列清空
        logger.info(f"⏳ 等待 {self._summary_queue.qsize()} 个 Summary 任务完成...")
        await self._summary_queue.join()
        
        # 发送停止信号
        for _ in range(self._summary_worker_count):
            await self._summary_queue.put(None)
        
        # 等待 workers 退出
        await asyncio.gather(*self._summary_workers, return_exceptions=True)
        logger.info("✅ 所有 Summary 任务已完成")


# ============================================================================
# 清单管理
# ============================================================================

class ManifestManager:
    """管理任务清单"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.manifest_file = self.output_dir / "manifest.json"
    
    def save(self, tasks: List[TaskDefinition], config: Dict):
        """保存任务清单"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        manifest = {
            'version': '2.0',
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


# ============================================================================
# 命令处理
# ============================================================================

def cmd_generate(args):
    """生成任务清单"""
    output_dir = Path(args.output)
    
    if output_dir.exists() and (output_dir / "manifest.json").exists():
        if not args.force:
            logger.error(f"输出目录已存在: {output_dir}")
            logger.error("使用 --force 覆盖")
            return
    
    generator = TaskGenerator()
    tasks = generator.generate(total=args.total, batch_size=args.batch_size)
    
    config = {
        'total': args.total,
        'batch_size': args.batch_size,
        'max_workers': args.max_workers,
        'generated_at': datetime.now().isoformat()
    }
    
    manifest = ManifestManager(output_dir)
    manifest.save(tasks, config)
    
    # 打印统计
    _print_task_stats(tasks)


def cmd_preview(args):
    """预览任务分布"""
    output_dir = Path(args.dir)
    manifest = ManifestManager(output_dir)
    tasks, config = manifest.load()
    
    _print_task_stats(tasks)
    
    # 打印配置
    print(f"\n配置:")
    print(f"  总数: {config.get('total')}")
    print(f"  批大小: {config.get('batch_size')}")
    print(f"  并发数: {config.get('max_workers', 5)}")


def cmd_run(args):
    """执行生成"""
    output_dir = Path(args.dir)
    manifest = ManifestManager(output_dir)
    tasks, config = manifest.load()
    
    executor = BatchExecutor(
        output_dir=output_dir,
        batch_size=config.get('batch_size', 200),
        max_workers=args.max_workers or config.get('max_workers', 5),
        max_retries=args.retries,
        generate_summary=not args.no_summary,
        total_tasks=len(tasks)
    )
    
    executor.run(tasks, retry_failed=False)


def cmd_status(args):
    """查看进度"""
    output_dir = Path(args.dir)
    manifest = ManifestManager(output_dir)
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
    completed_width = int(bar_width * completed / total)
    failed_width = int(bar_width * failed / total)
    pending_width = bar_width - completed_width - failed_width
    
    bar = '█' * completed_width + '▓' * failed_width + '░' * pending_width
    print(f"\n[{bar}] {completed/total*100:.1f}%")
    print(f"{'='*60}\n")


def cmd_retry(args):
    """重试失败任务"""
    output_dir = Path(args.dir)
    manifest = ManifestManager(output_dir)
    tasks, config = manifest.load()
    
    executor = BatchExecutor(
        output_dir=output_dir,
        batch_size=config.get('batch_size', 200),
        max_workers=args.max_workers or config.get('max_workers', 5),
        max_retries=args.retries,
        generate_summary=not args.no_summary,
        total_tasks=len(tasks)
    )
    
    executor.run(tasks, retry_failed=True)


def cmd_report(args):
    """生成最终报告"""
    output_dir = Path(args.dir)
    manifest = ManifestManager(output_dir)
    tasks, config = manifest.load()
    
    progress = ProgressManager(output_dir)
    
    # 收集统计
    stats = {
        'total': len(tasks),
        'completed': len(progress.completed_ids),
        'failed': len(progress.failed_ids),
        'by_language': defaultdict(lambda: {'completed': 0, 'failed': 0}),
        'by_chart_type': defaultdict(lambda: {'completed': 0, 'failed': 0}),
        'by_theme': defaultdict(lambda: {'completed': 0, 'failed': 0}),
        'by_style': defaultdict(lambda: {'completed': 0, 'failed': 0}),
        'by_data_source': defaultdict(lambda: {'completed': 0, 'failed': 0}),
    }
    
    for task in tasks:
        status = 'completed' if task.task_id in progress.completed_ids else \
                 'failed' if task.task_id in progress.failed_ids else 'pending'
        if status in ['completed', 'failed']:
            stats['by_language'][task.language][status] += 1
            stats['by_chart_type'][task.chart_type][status] += 1
            stats['by_theme'][task.theme][status] += 1
            stats['by_style'][task.visual_style][status] += 1
            stats['by_data_source'][task.data_source][status] += 1
    
    # 保存报告
    report_file = output_dir / "report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False, default=dict)
    
    logger.info(f"报告已保存: {report_file}")
    
    # 打印摘要
    print(f"\n{'='*60}")
    print(f"最终报告: {output_dir.name}")
    print(f"{'='*60}")
    print(f"总计: {stats['total']}")
    print(f"完成: {stats['completed']} ({stats['completed']/stats['total']*100:.1f}%)")
    print(f"失败: {stats['failed']} ({stats['failed']/stats['total']*100:.1f}%)")
    
    print(f"\n按数据源:")
    for source, counts in stats['by_data_source'].items():
        total_source = counts['completed'] + counts['failed']
        print(f"  {source}: {counts['completed']}/{total_source} 成功")
    
    print(f"{'='*60}\n")


def _print_task_stats(tasks: List[TaskDefinition]):
    """打印任务统计"""
    print(f"\n{'='*60}")
    print(f"任务统计: {len(tasks)} 个任务")
    print(f"{'='*60}")
    
    # 按语言
    by_lang = defaultdict(int)
    for t in tasks:
        by_lang[t.language] += 1
    print(f"\n语言分布:")
    for lang, count in sorted(by_lang.items()):
        print(f"  {lang}: {count} ({count/len(tasks)*100:.1f}%)")
    
    # 按数据源
    by_source = defaultdict(int)
    for t in tasks:
        by_source[t.data_source] += 1
    print(f"\n数据源分布:")
    for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {source}: {count} ({count/len(tasks)*100:.1f}%)")
    
    # 按图表类型
    by_chart = defaultdict(int)
    for t in tasks:
        by_chart[t.chart_type] += 1
    print(f"\n图表类型 (Top 10):")
    for chart, count in sorted(by_chart.items(), key=lambda x: -x[1])[:10]:
        print(f"  {chart}: {count} ({count/len(tasks)*100:.1f}%)")
    
    # 按主题
    by_theme = defaultdict(int)
    for t in tasks:
        by_theme[t.theme] += 1
    print(f"\n主题分布 (Top 10):")
    for theme, count in sorted(by_theme.items(), key=lambda x: -x[1])[:10]:
        print(f"  {theme}: {count} ({count/len(tasks)*100:.1f}%)")
    
    # 按视觉风格
    by_style = defaultdict(int)
    for t in tasks:
        by_style[t.visual_style] += 1
    print(f"\n视觉风格:")
    for style, count in sorted(by_style.items(), key=lambda x: -x[1]):
        print(f"  {style}: {count} ({count/len(tasks)*100:.1f}%)")
    
    # 批次数
    max_batch = max(t.batch_index for t in tasks)
    print(f"\n批次数: {max_batch}")
    print(f"{'='*60}\n")


# ============================================================================
# 主函数
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='生产级批量图表生成脚本（高并发）',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # generate 子命令
    gen_parser = subparsers.add_parser('generate', help='生成任务清单')
    gen_parser.add_argument('--total', type=int, default=4000, help='总任务数')
    gen_parser.add_argument('--batch-size', type=int, default=200, help='每批大小')
    gen_parser.add_argument('--max-workers', type=int, default=5, help='并发数')
    gen_parser.add_argument('--output', required=True, help='输出目录')
    gen_parser.add_argument('--force', action='store_true', help='强制覆盖')
    
    # preview 子命令
    preview_parser = subparsers.add_parser('preview', help='预览任务分布')
    preview_parser.add_argument('--dir', required=True, help='任务目录')
    
    # run 子命令
    run_parser = subparsers.add_parser('run', help='执行生成')
    run_parser.add_argument('--dir', required=True, help='任务目录')
    run_parser.add_argument('--max-workers', type=int, help='并发数')
    run_parser.add_argument('--retries', type=int, default=3, help='最大重试次数')
    run_parser.add_argument('--no-summary', action='store_true', help='不生成图片摘要')
    
    # status 子命令
    status_parser = subparsers.add_parser('status', help='查看进度')
    status_parser.add_argument('--dir', required=True, help='任务目录')
    
    # retry 子命令
    retry_parser = subparsers.add_parser('retry', help='重试失败任务')
    retry_parser.add_argument('--dir', required=True, help='任务目录')
    retry_parser.add_argument('--max-workers', type=int, help='并发数')
    retry_parser.add_argument('--retries', type=int, default=3, help='最大重试次数')
    retry_parser.add_argument('--no-summary', action='store_true', help='不生成图片摘要')
    
    # report 子命令
    report_parser = subparsers.add_parser('report', help='生成最终报告')
    report_parser.add_argument('--dir', required=True, help='任务目录')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    try:
        if args.command == 'generate':
            cmd_generate(args)
        elif args.command == 'preview':
            cmd_preview(args)
        elif args.command == 'run':
            cmd_run(args)
        elif args.command == 'status':
            cmd_status(args)
        elif args.command == 'retry':
            cmd_retry(args)
        elif args.command == 'report':
            cmd_report(args)
    except Exception as e:
        logger.error(f"执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
