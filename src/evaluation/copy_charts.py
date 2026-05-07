#!/usr/bin/env python3
"""复制图表文件夹到 sync_300_cn 和 sync_300_en"""
import shutil
from pathlib import Path

SOURCE_DIR = Path("<WORKSPACE>/合成图表/chart-synthesis-v4/output/batch_1000_final")
TARGET_CN = Path("$DATA_ROOT/benchmark/data/sync_300_cn")
TARGET_EN = Path("$DATA_ROOT/benchmark/data/sync_300_en")

def copy_charts(source_dir, target_dir, lang_pattern, target_count=300):
    """复制有图的文件夹"""
    existing = len(list(target_dir.iterdir())) if target_dir.exists() else 0
    need = target_count - existing
    print(f"{target_dir.name}: 已有 {existing}, 需补充 {need}")

    if need <= 0:
        print(f"  已满足 {target_count} 张，跳过")
        return 0

    copied = 0
    for folder in sorted(source_dir.glob(f"*_{lang_pattern}_*")):
        if copied >= need:
            break

        chart_file = folder / "artifacts" / "chart.png"
        if not chart_file.exists():
            continue

        target_folder = target_dir / folder.name
        if target_folder.exists():
            continue

        # 创建目标文件夹并复制
        target_folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(chart_file, target_folder / "chart.png")

        # 如果有 analysis.txt 也复制
        analysis_file = folder / "summary" / "analysis.txt"
        if analysis_file.exists():
            shutil.copy2(analysis_file, target_folder / "analysis.txt")

        copied += 1

    final_count = len(list(target_dir.iterdir()))
    print(f"  已复制 {copied} 个，当前总数: {final_count}")
    return copied

if __name__ == "__main__":
    print("=== 复制图表文件夹 ===\n")

    # 复制中文
    copy_charts(SOURCE_DIR, TARGET_CN, "zh-CN", 300)
    print()

    # 复制英文
    copy_charts(SOURCE_DIR, TARGET_EN, "en-US", 300)
    print()

    print("=== 完成 ===")
