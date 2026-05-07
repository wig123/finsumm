#!/usr/bin/env python3
"""
统一数据转换脚本 - 将所有训练数据转换为 LLaMA-Factory ShareGPT 格式

数据源:
1. 合成图表 (synthesis): 三个目录
   - production_4000_v2/summaries
   - production_4000/summaries  
   - prog_2000/summaries

2. 真实金融图表 (fin-chart): data/fin-chart 目录

3. FinMME 图表 (finmme): data/finmme 目录

输出:
- all_train.json: 合并的训练集
- all_val.json: 合并的验证集
- dataset_info.json: LLaMA-Factory 配置
"""

import json
import os
import shutil
import random
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from tqdm import tqdm
from PIL import Image
import math

# ============== 配置 ==============

# Benchmark 排除列表目录
BENCHMARK_DIR = Path("$DATA_ROOT/benchmark/data")

# fin-chart 和 finmme 训练数据目录 (已排除 benchmark)
FIN_CHART_SOURCE_DIR = Path("$DATA_ROOT/sft/data/fin-chart")
FINMME_SOURCE_DIR = Path("$DATA_ROOT/sft/data/finmme")

@dataclass
class DataSource:
    """数据源配置"""
    name: str
    source_dir: Path
    image_field: str  # 图片文件名字段 (chart.png 或 {id}.png/jpg)
    analysis_field: str  # 分析文本文件名
    prefix: str  # 输出图片前缀
    lang_detect: str  # 语言检测方式: "dirname" 或 "fixed_zh" 或 "fixed_en"

# 合成图表数据源 (v3)
SYNTHESIS_SOURCES_V3 = [
    DataSource(
        name="production_4000_v2",
        source_dir=Path("<WORKSPACE>/合成图表/chart-synthesis-v3/production_4000_v2/summaries"),
        image_field="chart.png",
        analysis_field="analysis.txt",
        prefix="syn_v2_",
        lang_detect="dirname"
    ),
    DataSource(
        name="production_4000",
        source_dir=Path("<WORKSPACE>/合成图表/chart-synthesis-v3/production_4000/summaries"),
        image_field="chart.png",
        analysis_field="analysis.txt",
        prefix="syn_",
        lang_detect="dirname"
    ),
    DataSource(
        name="prog_2000",
        source_dir=Path("<WORKSPACE>/合成图表/chart-synthesis-v3/prog_2000/summaries"),
        image_field="chart.png",
        analysis_field="analysis.txt",
        prefix="prog_",
        lang_detect="dirname"
    ),
]

# 合成图表数据源 (v4) - 需要排除 benchmark 样本
SYNTHESIS_SOURCES_V4 = [
    DataSource(
        name="batch_1000_final",
        source_dir=Path("<WORKSPACE>/合成图表/chart-synthesis-v4/output/batch_1000_final"),
        image_field="artifacts/chart.png",
        analysis_field="summary/analysis.txt",
        prefix="syn_v4f_",
        lang_detect="dirname"
    ),
    DataSource(
        name="batch_2000",
        source_dir=Path("<WORKSPACE>/合成图表/chart-synthesis-v4/output/batch_2000"),
        image_field="artifacts/chart.png",
        analysis_field="summary/analysis.txt",
        prefix="syn_v4_",
        lang_detect="dirname"
    ),
]

# 输出目录
OUTPUT_DIR = Path("$DATA_ROOT/sft/data")
IMAGES_DIR = OUTPUT_DIR / "images"

# 训练/验证集划分比例
# 对于中小型数据集 (~5000 样本)，推荐 80/20 划分
# 20% 验证集能提供更稳定的评估，约 1000 个样本足够代表数据分布
TRAIN_RATIO = 0.8
RANDOM_SEED = 42

# 图片大小限制 (像素总数)
# 2M pixels = 2,000,000 (例如 1414x1414 或 1600x1250)
MAX_PIXELS = 2_000_000

# 数据源采样限制 (平衡数据集)
SOURCE_SAMPLE_LIMITS = {
    "production_4000_v2": 1000,  # 原 1363 -> 1000
    "prog_2000": 1000,           # 原 1161 -> 1000
}

# ============== Prompts ==============

SYSTEM_PROMPT_EN = "You are a financial chart analyst. Analyze the given financial chart and provide detailed insights."
SYSTEM_PROMPT_ZH = "你是一位金融图表分析师。请分析给定的金融图表并提供详细的见解。"

USER_PROMPT_EN = "Please analyze this financial chart in detail."
USER_PROMPT_ZH = "请详细分析这张金融图表。"

# ============== Benchmark 排除列表 ==============

def load_benchmark_exclusions() -> Dict[str, set]:
    """加载 benchmark 排除列表"""
    exclusions = {
        "sync_300": set(),      # v3 + v4 合成图表 benchmark 样本名
        "fin_chart": set(),     # fin-chart benchmark 样本名
        "finmme": set(),        # finmme benchmark 样本名
    }

    # 加载 sync_300_cn 和 sync_300_en
    for lang in ["cn", "en"]:
        sync_dir = BENCHMARK_DIR / f"sync_300_{lang}"
        if sync_dir.exists():
            for d in sync_dir.iterdir():
                if d.is_dir():
                    exclusions["sync_300"].add(d.name)

    # 加载 fin-chart_200
    fin_chart_benchmark = BENCHMARK_DIR / "fin-chart_200"
    if fin_chart_benchmark.exists():
        for d in fin_chart_benchmark.iterdir():
            if d.is_dir():
                exclusions["fin_chart"].add(d.name)

    # 加载 finmme_200
    finmme_benchmark = BENCHMARK_DIR / "finmme_200"
    if finmme_benchmark.exists():
        for d in finmme_benchmark.iterdir():
            if d.is_dir():
                exclusions["finmme"].add(d.name)

    print(f"📋 Benchmark 排除列表:")
    print(f"  - sync_300: {len(exclusions['sync_300'])} 个样本")
    print(f"  - fin-chart: {len(exclusions['fin_chart'])} 个样本")
    print(f"  - finmme: {len(exclusions['finmme'])} 个样本")

    return exclusions

# ============== 转换函数 ==============

def copy_and_resize_image(src_path: Path, dst_path: Path, max_pixels: int = MAX_PIXELS) -> bool:
    """复制图片，如果超过 max_pixels 则等比例缩小"""
    try:
        with Image.open(src_path) as img:
            width, height = img.size
            pixels = width * height

            if pixels > max_pixels:
                # 计算缩放比例
                scale = math.sqrt(max_pixels / pixels)
                new_width = int(width * scale)
                new_height = int(height * scale)

                # 使用高质量缩放
                img_resized = img.resize((new_width, new_height), Image.LANCZOS)
                img_resized.save(dst_path, quality=95 if dst_path.suffix.lower() in ['.jpg', '.jpeg'] else None)
            else:
                # 直接复制
                shutil.copy2(src_path, dst_path)
        return True
    except Exception as e:
        print(f"    ⚠️  图片处理失败 {src_path}: {e}")
        return False

def detect_language(dir_name: str, method: str) -> str:
    """检测语言"""
    if method == "dirname":
        if "zh-CN" in dir_name:
            return "zh"
        elif "en-US" in dir_name:
            return "en"
        else:
            return "en"  # 默认英文
    elif method == "fixed_zh":
        return "zh"
    elif method == "fixed_en":
        return "en"
    else:
        return "en"

def build_sample(
    image_path: str,
    analysis: str,
    lang: str
) -> Dict:
    """构建 ShareGPT 格式样本"""
    if lang == "zh":
        system_prompt = SYSTEM_PROMPT_ZH
        user_prompt = USER_PROMPT_ZH
    else:
        system_prompt = SYSTEM_PROMPT_EN
        user_prompt = USER_PROMPT_EN
    
    return {
        "messages": [
            {"from": "system", "value": system_prompt},
            {"from": "human", "value": f"<image>\n{user_prompt}"},
            {"from": "gpt", "value": analysis}
        ],
        "images": [image_path]
    }

def process_synthesis_source(source: DataSource, copy_images: bool = True, exclude_set: set = None, max_samples: int = None) -> List[Dict]:
    """处理合成图表数据源

    Args:
        source: 数据源配置
        copy_images: 是否复制图片
        exclude_set: 需要排除的样本名集合 (benchmark 数据)
        max_samples: 最大样本数限制，超过则随机采样
    """
    samples = []
    exclude_set = exclude_set or set()

    if not source.source_dir.exists():
        print(f"⚠️  目录不存在: {source.source_dir}")
        return samples

    # 遍历所有子目录
    all_subdirs = [d for d in source.source_dir.iterdir()
               if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")]

    # 排除 benchmark 样本
    subdirs = [d for d in all_subdirs if d.name not in exclude_set]
    excluded_count = len(all_subdirs) - len(subdirs)

    # 如果需要采样，先过滤出有效样本再采样
    sampled_info = ""
    if max_samples and len(subdirs) > max_samples:
        # 先验证哪些样本有效（有图片和分析文件）
        valid_subdirs = []
        for subdir in subdirs:
            image_file = subdir / source.image_field
            analysis_file = subdir / source.analysis_field
            # 英文样本也检查 analysis_en.txt
            if "en-US" in subdir.name:
                analysis_en_file = analysis_file.parent / "analysis_en.txt"
                if analysis_en_file.exists():
                    analysis_file = analysis_en_file
            if image_file.exists() and analysis_file.exists():
                try:
                    analysis = analysis_file.read_text(encoding="utf-8").strip()
                    if analysis:
                        valid_subdirs.append(subdir)
                except:
                    pass

        # 从有效样本中采样
        if len(valid_subdirs) > max_samples:
            random.seed(RANDOM_SEED)
            subdirs = random.sample(valid_subdirs, max_samples)
            sampled_info = f", 采样 {max_samples}/{len(valid_subdirs)} 有效"
        else:
            subdirs = valid_subdirs
            sampled_info = f", 有效 {len(valid_subdirs)}"

    print(f"📂 处理 {source.name}: {len(subdirs)} 个样本 (排除 {excluded_count} 个 benchmark{sampled_info})")
    
    for subdir in tqdm(subdirs, desc=f"  {source.name}"):
        dir_name = subdir.name

        # 检查必需文件
        image_file = subdir / source.image_field

        # 检测语言
        lang = detect_language(dir_name, source.lang_detect)

        # 根据语言选择分析文件
        # 英文样本优先使用 analysis_en.txt (V4 数据有双语版本)
        analysis_file = subdir / source.analysis_field
        if lang == "en" and "en-US" in dir_name:
            # 尝试使用英文分析文件
            analysis_en_file = analysis_file.parent / "analysis_en.txt"
            if analysis_en_file.exists():
                analysis_file = analysis_en_file

        if not image_file.exists():
            continue
        if not analysis_file.exists():
            continue

        # 读取分析文本
        try:
            analysis = analysis_file.read_text(encoding="utf-8").strip()
        except Exception as e:
            print(f"    ⚠️  读取失败 {analysis_file}: {e}")
            continue

        if not analysis:
            continue
        
        # 生成输出图片名
        output_image_name = f"{source.prefix}{dir_name}.png"
        output_image_path = IMAGES_DIR / output_image_name
        
        # 复制图片 (强制覆盖以更新尺寸)
        if copy_images:
            copy_and_resize_image(image_file, output_image_path)

        # 构建样本
        sample = build_sample(
            image_path=f"images/{output_image_name}",
            analysis=analysis,
            lang=lang
        )
        samples.append(sample)

    return samples

def process_fin_chart(copy_images: bool = True, exclude_set: set = None) -> List[Dict]:
    """处理 fin-chart 数据 (从训练数据目录，排除 benchmark)"""
    samples = []
    exclude_set = exclude_set or set()
    fin_chart_dir = FIN_CHART_SOURCE_DIR

    if not fin_chart_dir.exists():
        print(f"⚠️  fin-chart 训练数据目录不存在: {fin_chart_dir}")
        return samples

    all_subdirs = [d for d in fin_chart_dir.iterdir() if d.is_dir() and d.name.startswith("mc_")]
    subdirs = [d for d in all_subdirs if d.name not in exclude_set]
    excluded_count = len(all_subdirs) - len(subdirs)
    print(f"📂 处理 fin-chart: {len(subdirs)} 个样本 (排除 {excluded_count} 个 benchmark)")
    
    for subdir in tqdm(subdirs, desc="  fin-chart"):
        sample_id = subdir.name

        # 查找图片 (jpg 格式，文件名与目录名相同)
        image_file = subdir / f"{sample_id}.jpg"
        if not image_file.exists():
            # 尝试查找任何 jpg 文件
            jpg_files = list(subdir.glob("*.jpg"))
            if not jpg_files:
                continue
            image_file = jpg_files[0]

        # 优先使用英文分析
        analysis_file = subdir / "analysis_en.txt"
        if not analysis_file.exists():
            analysis_file = subdir / "analysis.txt"

        if not analysis_file.exists():
            continue

        try:
            analysis = analysis_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue

        if not analysis:
            continue

        # 输出图片名 (使用 mc_ 前缀)
        output_image_name = f"{sample_id}.jpg"
        output_image_path = IMAGES_DIR / output_image_name

        # 复制图片 (强制覆盖以更新尺寸)
        if copy_images:
            copy_and_resize_image(image_file, output_image_path)

        # fin-chart 使用英文
        sample = build_sample(
            image_path=f"images/{output_image_name}",
            analysis=analysis,
            lang="en"
        )
        samples.append(sample)

    return samples

def process_finmme(copy_images: bool = True, exclude_set: set = None) -> List[Dict]:
    """处理 finmme 数据 (从训练数据目录，排除 benchmark)"""
    samples = []
    exclude_set = exclude_set or set()
    finmme_dir = FINMME_SOURCE_DIR

    if not finmme_dir.exists():
        print(f"⚠️  finmme 训练数据目录不存在: {finmme_dir}")
        return samples

    all_subdirs = [d for d in finmme_dir.iterdir() if d.is_dir() and d.name.startswith("finmme_")]
    subdirs = [d for d in all_subdirs if d.name not in exclude_set]
    excluded_count = len(all_subdirs) - len(subdirs)
    print(f"📂 处理 finmme: {len(subdirs)} 个样本 (排除 {excluded_count} 个 benchmark)")

    for subdir in tqdm(subdirs, desc="  finmme"):
        sample_id = subdir.name

        # 查找图片 (png 格式，文件名与目录名相同)
        image_file = subdir / f"{sample_id}.png"
        if not image_file.exists():
            # 尝试查找任何 png 文件
            png_files = list(subdir.glob("*.png"))
            if not png_files:
                continue
            image_file = png_files[0]

        # 优先使用英文分析
        analysis_file = subdir / "analysis_en.txt"
        if not analysis_file.exists():
            analysis_file = subdir / "analysis.txt"

        if not analysis_file.exists():
            continue

        try:
            analysis = analysis_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue

        if not analysis:
            continue

        # 输出图片名
        output_image_name = f"{sample_id}.png"
        output_image_path = IMAGES_DIR / output_image_name

        # 复制图片 (强制覆盖以更新尺寸)
        if copy_images:
            copy_and_resize_image(image_file, output_image_path)

        # finmme 使用英文
        sample = build_sample(
            image_path=f"images/{output_image_name}",
            analysis=analysis,
            lang="en"
        )
        samples.append(sample)

    return samples

def split_dataset(samples: List[Dict], train_ratio: float = 0.8, seed: int = 42) -> tuple:
    """划分训练/验证集"""
    random.seed(seed)
    shuffled = samples.copy()
    random.shuffle(shuffled)
    
    split_idx = int(len(shuffled) * train_ratio)
    return shuffled[:split_idx], shuffled[split_idx:]

def save_dataset(samples: List[Dict], filepath: Path):
    """保存数据集"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 已保存: {filepath} ({len(samples)} 条)")

def generate_dataset_info():
    """生成 dataset_info.json"""
    config = {
        "all_train": {
            "file_name": "all_train.json",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            }
        },
        "all_val": {
            "file_name": "all_val.json",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            }
        },
        "synthesis_train": {
            "file_name": "synthesis_train.json",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            }
        },
        "synthesis_val": {
            "file_name": "synthesis_val.json",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            }
        },
        "chart_train": {
            "file_name": "chart_train.json",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            }
        },
        "chart_val": {
            "file_name": "chart_val.json",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            }
        }
    }
    
    config_path = OUTPUT_DIR / "dataset_info.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 已更新: {config_path}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="统一数据转换脚本")
    parser.add_argument("--no-copy", action="store_true", help="不复制图片（仅生成 JSON）")
    parser.add_argument("--synthesis-only", action="store_true", help="仅处理合成图表")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="训练集比例 (推荐 0.8)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚀 统一数据转换脚本")
    print("=" * 60)

    # 确保输出目录存在
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 加载 benchmark 排除列表
    print("\n📋 加载 Benchmark 排除列表...")
    exclusions = load_benchmark_exclusions()

    all_samples = []
    synthesis_samples = []

    # 1. 处理合成图表数据 (v3) - 排除 benchmark 样本
    print("\n📦 处理合成图表数据 (v3)...")
    for source in SYNTHESIS_SOURCES_V3:
        samples = process_synthesis_source(
            source,
            copy_images=not args.no_copy,
            exclude_set=exclusions["sync_300"],
            max_samples=SOURCE_SAMPLE_LIMITS.get(source.name)
        )
        synthesis_samples.extend(samples)
        all_samples.extend(samples)

    print(f"  v3 合成图表: {len(synthesis_samples)} 个样本")

    # 2. 处理合成图表数据 (v4) - 排除 benchmark 样本
    print("\n📦 处理合成图表数据 (v4)...")
    v4_count_before = len(synthesis_samples)
    for source in SYNTHESIS_SOURCES_V4:
        samples = process_synthesis_source(
            source,
            copy_images=not args.no_copy,
            exclude_set=exclusions["sync_300"]
        )
        synthesis_samples.extend(samples)
        all_samples.extend(samples)

    print(f"  v4 合成图表: {len(synthesis_samples) - v4_count_before} 个样本")
    print(f"\n  合成图表总计: {len(synthesis_samples)} 个样本")

    # 统计语言分布
    zh_count = sum(1 for s in synthesis_samples if "zh-CN" in s["images"][0] or "分析" in s["messages"][0]["value"])
    en_count = len(synthesis_samples) - zh_count
    print(f"  语言分布 (估算): 中文 ~{zh_count}, 英文 ~{en_count}")

    if not args.synthesis_only:
        # 3. 处理 fin-chart 数据 - 排除 benchmark 样本
        print("\n📦 处理 fin-chart 数据...")
        fin_chart_samples = process_fin_chart(
            copy_images=not args.no_copy,
            exclude_set=exclusions["fin_chart"]
        )
        all_samples.extend(fin_chart_samples)
        print(f"  fin-chart 总计: {len(fin_chart_samples)} 个样本")

        # 4. 处理 finmme 数据 - 排除 benchmark 样本
        print("\n📦 处理 finmme 数据...")
        finmme_samples = process_finmme(
            copy_images=not args.no_copy,
            exclude_set=exclusions["finmme"]
        )
        all_samples.extend(finmme_samples)
        print(f"  finmme 总计: {len(finmme_samples)} 个样本")
    
    print(f"\n📊 总样本数: {len(all_samples)}")
    
    # 划分数据集
    print("\n📝 划分数据集...")
    
    # 合成图表单独划分
    syn_train, syn_val = split_dataset(synthesis_samples, args.train_ratio, args.seed)
    save_dataset(syn_train, OUTPUT_DIR / "synthesis_train.json")
    save_dataset(syn_val, OUTPUT_DIR / "synthesis_val.json")
    
    # 全部数据划分
    all_train, all_val = split_dataset(all_samples, args.train_ratio, args.seed)
    save_dataset(all_train, OUTPUT_DIR / "all_train.json")
    save_dataset(all_val, OUTPUT_DIR / "all_val.json")
    
    # 更新 dataset_info.json
    print("\n⚙️  更新配置...")
    generate_dataset_info()
    
    print("\n" + "=" * 60)
    print("✅ 转换完成!")
    print("=" * 60)
    print(f"""
📊 数据集统计:
  - synthesis_train: {len(syn_train)} 条
  - synthesis_val: {len(syn_val)} 条
  - all_train: {len(all_train)} 条
  - all_val: {len(all_val)} 条

📁 输出文件:
  - {OUTPUT_DIR}/synthesis_train.json
  - {OUTPUT_DIR}/synthesis_val.json
  - {OUTPUT_DIR}/all_train.json
  - {OUTPUT_DIR}/all_val.json
  - {OUTPUT_DIR}/dataset_info.json
  - {IMAGES_DIR}/ (图片目录)

🔧 下一步:
  1. 检查数据: head -50 {OUTPUT_DIR}/all_train.json
  2. 更新训练配置中的 dataset 字段
  3. 开始训练
""")

if __name__ == "__main__":
    main()

