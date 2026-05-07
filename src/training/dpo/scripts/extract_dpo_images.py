#!/usr/bin/env python3
"""
提取 DPO 训练所需的图片到单独目录，方便上传到 AutoDL
"""

import json
import shutil
from pathlib import Path
import argparse


def extract_images(
    dpo_data_file: Path,
    source_images_dir: Path,
    output_dir: Path
):
    """提取 DPO 数据集用到的图片"""

    # 加载 DPO 数据
    with open(dpo_data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"DPO 样本数: {len(data)}")

    # 创建输出目录
    output_images_dir = output_dir / "images"
    output_images_dir.mkdir(parents=True, exist_ok=True)

    # 复制图片
    copied = 0
    missing = 0
    for item in data:
        for img_path in item.get('images', []):
            # 去掉 "images/" 前缀
            if img_path.startswith('images/'):
                img_name = img_path[7:]
            else:
                img_name = img_path

            src = source_images_dir / img_name
            dst = output_images_dir / img_name

            if src.exists():
                shutil.copy2(src, dst)
                copied += 1
            else:
                print(f"警告: 图片不存在 {src}")
                missing += 1

    print(f"\n复制完成: {copied} 张图片")
    if missing:
        print(f"缺失: {missing} 张")

    # 复制 DPO 数据文件
    shutil.copy2(dpo_data_file, output_dir / "dpo_train_100.json")

    # 创建 dataset_info.json
    dataset_info = {
        "dpo_train_100": {
            "file_name": "dpo_train_100.json",
            "formatting": "sharegpt",
            "ranking": True,
            "columns": {
                "messages": "conversations",
                "chosen": "chosen",
                "rejected": "rejected",
                "images": "images"
            }
        }
    }
    with open(output_dir / "dataset_info.json", 'w', encoding='utf-8') as f:
        json.dump(dataset_info, f, ensure_ascii=False, indent=2)

    print(f"\n输出目录: {output_dir}")
    print(f"  - dpo_train_100.json")
    print(f"  - dataset_info.json")
    print(f"  - images/ ({copied} 张)")

    # 统计大小
    total_size = sum(f.stat().st_size for f in output_dir.rglob('*') if f.is_file())
    print(f"\n总大小: {total_size / 1024 / 1024:.1f} MB")


def main():
    parser = argparse.ArgumentParser(description="提取 DPO 训练图片")
    parser.add_argument(
        '--dpo-data', type=Path,
        default=Path('$DATA_ROOT/sft/data/dpo_train_100.json'),
        help='DPO 数据文件'
    )
    parser.add_argument(
        '--source-images', type=Path,
        default=Path('$DATA_ROOT/sft/data/images'),
        help='源图片目录'
    )
    parser.add_argument(
        '--output', type=Path,
        default=Path('$DATA_ROOT/dpo/data/autodl_upload'),
        help='输出目录'
    )

    args = parser.parse_args()
    extract_images(args.dpo_data, args.source_images, args.output)


if __name__ == '__main__':
    main()
