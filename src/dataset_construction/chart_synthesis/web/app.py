#!/usr/bin/env python3
"""图表查看器 - chart-synthesis-v4"""

import json
import shutil
import re
from pathlib import Path
from flask import Flask, render_template, send_from_directory, abort, request, jsonify

app = Flask(__name__)

# 配置
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output" / "batch_2000"
DELETED_DIR = OUTPUT_DIR / "_deleted"
PAGE_SIZE = 100


def parse_folder_name(folder_name):
    """解析文件夹名: 20251211_210753_heatmap_en-US_fx_trade_10151860
    格式: {timestamp}_{chart_type}_{language}_{theme}_{hash}
    """
    # 使用正则匹配语言代码 (en-US, zh-CN 等)
    lang_match = re.search(r'_(en-US|zh-CN|ja-JP|ko-KR|de-DE|fr-FR)_', folder_name)
    if not lang_match:
        return "unknown", "unknown", "unknown", folder_name[:8] if len(folder_name) > 8 else folder_name

    language = lang_match.group(1)
    lang_pos = lang_match.start()
    lang_end = lang_match.end()

    # timestamp 和 chart_type 在 language 之前
    prefix = folder_name[:lang_pos]
    # 格式: 20251211_210753_heatmap
    parts = prefix.split('_')
    # 前两个是 timestamp，剩下的是 chart_type
    if len(parts) >= 3:
        timestamp = f"{parts[0]}_{parts[1]}"  # 20251211_210753
        chart_type = '_'.join(parts[2:])  # heatmap 或 bollinger_bands
    else:
        timestamp = parts[0] if parts else "unknown"
        chart_type = "unknown"

    # theme 和 hash 在 language 之后
    suffix = folder_name[lang_end - 1:]  # _fx_trade_10151860
    if suffix.startswith('_'):
        suffix = suffix[1:]  # fx_trade_10151860

    suffix_parts = suffix.rsplit('_', 1)
    if len(suffix_parts) == 2:
        theme = suffix_parts[0]  # fx_trade
        chart_hash = suffix_parts[1]  # 10151860
    else:
        theme = suffix
        chart_hash = ""

    return chart_type, language, theme, timestamp


def get_all_charts(page=1, show_deleted=False):
    """获取所有图表，带分页"""
    all_charts = []
    target_dir = DELETED_DIR if show_deleted else OUTPUT_DIR

    if not target_dir.exists():
        return [], 0, 0

    # 按文件夹名排序（时间戳在前，自然按时间排序）
    for chart_dir in sorted(target_dir.iterdir(), key=lambda x: x.name, reverse=True):
        if not chart_dir.is_dir() or chart_dir.name.startswith('.') or chart_dir.name.startswith('_'):
            continue

        # 跳过非图表目录
        if chart_dir.name in ['logs', 'reports', 'status']:
            continue

        # 检查图片是否存在
        image_path = chart_dir / "artifacts" / "chart.png"
        if not image_path.exists():
            continue

        chart_type, language, theme, timestamp = parse_folder_name(chart_dir.name)

        # 尝试读取 metadata.json 获取更多信息
        metadata = {}
        metadata_path = chart_dir / "metadata.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            except:
                pass

        all_charts.append({
            "folder": chart_dir.name,
            "image": "artifacts/chart.png",
            "chart_type": metadata.get("chart_type", chart_type),
            "theme": metadata.get("theme", theme),
            "language": metadata.get("language", language),
            "timestamp": timestamp,
            "task_id": metadata.get("task_id", ""),
            "question": metadata.get("question", ""),
            "visual_style": metadata.get("visual_style", ""),
        })

    total = len(all_charts)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total > 0 else 1

    # 分页
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    charts = all_charts[start:end]

    return charts, total, total_pages


def get_stats(show_deleted=False):
    """获取统计信息"""
    stats = {"chart_types": {}, "themes": {}, "languages": {}, "visual_styles": {}, "total": 0}
    target_dir = DELETED_DIR if show_deleted else OUTPUT_DIR

    if not target_dir.exists():
        return stats

    for chart_dir in target_dir.iterdir():
        if not chart_dir.is_dir() or chart_dir.name.startswith('.') or chart_dir.name.startswith('_'):
            continue

        if chart_dir.name in ['logs', 'reports', 'status']:
            continue

        # 只统计有图片的
        if not (chart_dir / "artifacts" / "chart.png").exists():
            continue

        # 尝试从 metadata 获取信息
        metadata_path = chart_dir / "metadata.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
                chart_type = metadata.get("chart_type", "unknown")
                theme = metadata.get("theme", "unknown")
                language = metadata.get("language", "unknown")
                visual_style = metadata.get("visual_style", "unknown")
            except:
                chart_type, language, theme, _ = parse_folder_name(chart_dir.name)
                visual_style = "unknown"
        else:
            chart_type, language, theme, _ = parse_folder_name(chart_dir.name)
            visual_style = "unknown"

        stats["chart_types"][chart_type] = stats["chart_types"].get(chart_type, 0) + 1
        stats["themes"][theme] = stats["themes"].get(theme, 0) + 1
        stats["languages"][language] = stats["languages"].get(language, 0) + 1
        stats["visual_styles"][visual_style] = stats["visual_styles"].get(visual_style, 0) + 1
        stats["total"] += 1

    return stats


def get_deleted_count():
    """获取已删除项数量"""
    if not DELETED_DIR.exists():
        return 0
    count = 0
    for d in DELETED_DIR.iterdir():
        if d.is_dir() and not d.name.startswith('.'):
            if (d / "artifacts" / "chart.png").exists():
                count += 1
    return count


@app.route('/')
def index():
    """首页 - 图表列表"""
    page = request.args.get('page', 1, type=int)
    show_deleted = request.args.get('deleted', 'false') == 'true'

    charts, total, total_pages = get_all_charts(page, show_deleted)
    stats = get_stats(show_deleted)
    deleted_count = get_deleted_count()

    # 计算分页范围
    page_range = []
    if total_pages <= 10:
        page_range = list(range(1, total_pages + 1))
    else:
        start = max(1, page - 4)
        end = min(total_pages, page + 5)
        if start > 1:
            page_range.append(1)
            if start > 2:
                page_range.append('...')
        page_range.extend(range(start, end + 1))
        if end < total_pages:
            if end < total_pages - 1:
                page_range.append('...')
            page_range.append(total_pages)

    return render_template('index.html',
                          charts=charts,
                          stats=stats,
                          page=page,
                          total=total,
                          total_pages=total_pages,
                          page_range=page_range,
                          show_deleted=show_deleted,
                          deleted_count=deleted_count,
                          page_size=PAGE_SIZE)


@app.route('/images/<path:filename>')
def serve_image(filename):
    """提供图片文件"""
    return send_from_directory(OUTPUT_DIR, filename)


@app.route('/deleted_images/<path:filename>')
def serve_deleted_image(filename):
    """提供已删除的图片文件"""
    return send_from_directory(DELETED_DIR, filename)


@app.route('/api/delete_charts', methods=['POST'])
def delete_charts():
    """软删除选中的图表文件夹"""
    try:
        data = request.get_json()
        items = data.get('items', [])

        if not items:
            return jsonify({'success': False, 'error': '未选择任何图表'}), 400

        DELETED_DIR.mkdir(exist_ok=True)

        deleted = []
        failed = []

        for item in items:
            folder = item.get('folder', '')

            if '..' in folder or '/' in folder or '\\' in folder:
                failed.append({'folder': folder, 'reason': '无效的文件夹名称'})
                continue

            chart_dir = OUTPUT_DIR / folder
            if not chart_dir.exists():
                failed.append({'folder': folder, 'reason': '文件夹不存在'})
                continue

            try:
                dest = DELETED_DIR / folder
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.move(str(chart_dir), str(dest))
                deleted.append(folder)
            except Exception as e:
                failed.append({'folder': folder, 'reason': str(e)})

        return jsonify({
            'success': True,
            'deleted': deleted,
            'failed': failed,
            'deleted_count': len(deleted),
            'failed_count': len(failed)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/restore_charts', methods=['POST'])
def restore_charts():
    """恢复软删除的图表"""
    try:
        data = request.get_json()
        folders = data.get('folders', [])

        if not folders:
            return jsonify({'success': False, 'error': '未选择任何图表'}), 400

        restored = []
        failed = []

        for folder in folders:
            if '..' in folder or '/' in folder or '\\' in folder:
                failed.append({'folder': folder, 'reason': '无效的文件夹名称'})
                continue

            deleted_dir = DELETED_DIR / folder
            if not deleted_dir.exists():
                failed.append({'folder': folder, 'reason': '文件夹不存在'})
                continue

            try:
                dest = OUTPUT_DIR / folder
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.move(str(deleted_dir), str(dest))
                restored.append(folder)
            except Exception as e:
                failed.append({'folder': folder, 'reason': str(e)})

        return jsonify({
            'success': True,
            'restored': restored,
            'failed': failed,
            'restored_count': len(restored),
            'failed_count': len(failed)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get_detail/<path:folder>')
def get_detail(folder):
    """获取图表详细信息"""
    if '..' in folder:
        return jsonify({'success': False, 'error': '无效的文件夹名称'}), 400

    # 先检查正常目录，再检查已删除目录
    chart_dir = OUTPUT_DIR / folder
    if not chart_dir.exists():
        chart_dir = DELETED_DIR / folder

    if not chart_dir.exists():
        return jsonify({'success': False, 'error': '文件夹不存在'}), 404

    result = {}

    # 读取 metadata.json
    metadata_path = chart_dir / "metadata.json"
    if metadata_path.exists():
        try:
            content = metadata_path.read_text(encoding='utf-8')
            data = json.loads(content)
            result['metadata'] = json.dumps(data, indent=2, ensure_ascii=False)
        except Exception as e:
            result['metadata_error'] = str(e)

    # 读取 dataspec.json
    dataspec_path = chart_dir / "dataspec.json"
    if dataspec_path.exists():
        try:
            content = dataspec_path.read_text(encoding='utf-8')
            data = json.loads(content)
            result['dataspec'] = json.dumps(data, indent=2, ensure_ascii=False)
        except Exception as e:
            result['dataspec_error'] = str(e)

    # 读取代码
    code_path = chart_dir / "artifacts" / "code.py"
    if code_path.exists():
        try:
            result['code'] = code_path.read_text(encoding='utf-8')
        except Exception as e:
            result['code_error'] = str(e)

    # 读取数据摘要 (CSV 前几行)
    csv_path = chart_dir / "data" / "raw.csv"
    if csv_path.exists():
        try:
            lines = csv_path.read_text(encoding='utf-8').split('\n')[:20]
            result['data_preview'] = '\n'.join(lines)
        except Exception as e:
            result['data_error'] = str(e)

    if result:
        return jsonify({'success': True, **result})

    return jsonify({'success': False, 'error': '没有找到任何元数据文件'}), 404


@app.route('/api/permanent_delete', methods=['POST'])
def permanent_delete():
    """永久删除已软删除的图表"""
    try:
        data = request.get_json()
        folders = data.get('folders', [])

        if not folders:
            return jsonify({'success': False, 'error': '未选择任何图表'}), 400

        deleted = []
        failed = []

        for folder in folders:
            if '..' in folder or '/' in folder or '\\' in folder:
                failed.append({'folder': folder, 'reason': '无效的文件夹名称'})
                continue

            chart_dir = DELETED_DIR / folder
            if not chart_dir.exists():
                failed.append({'folder': folder, 'reason': '文件夹不存在'})
                continue

            try:
                shutil.rmtree(chart_dir)
                deleted.append(folder)
            except Exception as e:
                failed.append({'folder': folder, 'reason': str(e)})

        return jsonify({
            'success': True,
            'deleted': deleted,
            'failed': failed,
            'deleted_count': len(deleted),
            'failed_count': len(failed)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("图表查看器 - Chart Synthesis V4")
    print(f"访问地址: http://localhost:5004")
    print(f"输出目录: {OUTPUT_DIR}")
    stats = get_stats()
    print(f"图表总数: {stats['total']}")
    print(f"图表类型: {len(stats['chart_types'])}")
    print(f"主题数: {len(stats['themes'])}")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5004)
