"""
时间序列数据处理器 v2
====================
使用 pwlf 分段、scipy 极值检测、变点检测、波动体制等完整分析

参考: test_comprehensive_summary_v2.1.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Union, List, Dict, Any
from scipy.signal import find_peaks


def process_time_series(
    csv_path: Union[str, Path],
    data_points: int,
    max_raw: int = 200
) -> str:
    """
    处理时间序列数据

    Args:
        csv_path: CSV 文件路径
        data_points: 数据点数
        max_raw: 直接返回原始数据的阈值

    Returns:
        数据摘要字符串
    """
    df = pd.read_csv(csv_path)

    if data_points <= max_raw:
        return f"[原始数据 - {len(df)} 条]\n{df.to_string(index=False)}"

    # 长时间序列：生成结构化摘要
    return generate_ts_summary(df)


def generate_ts_summary(df: pd.DataFrame) -> str:
    """
    生成时间序列结构化摘要 (完整版)

    参考 test_comprehensive_summary_v2.1.py
    """
    # 识别日期列和数值列
    date_col, value_cols = identify_columns(df)

    # 解析日期并排序
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(date_col).reset_index(drop=True)

    sections = []

    # ========== 1. 基本信息 ==========
    sections.append(generate_basic_info(df, date_col, value_cols))

    # ========== 2. 全局统计 ==========
    for col in value_cols[:2]:  # 最多2个数值列
        sections.append(generate_global_stats(df, col, date_col))

    # ========== 3. 分段分析 (pwlf) ==========
    for col in value_cols[:1]:  # 只对第一个列
        seg_section = generate_segment_analysis(df, col, date_col)
        if seg_section:
            sections.append(seg_section)

    # ========== 4. 变点检测 ==========
    for col in value_cols[:1]:
        cp_section = generate_changepoints(df, col, date_col)
        if cp_section:
            sections.append(cp_section)

    # ========== 5. 极值点检测 ==========
    for col in value_cols[:1]:
        extrema_section = generate_extrema(df, col, date_col)
        if extrema_section:
            sections.append(extrema_section)

    # ========== 6. 波动体制 ==========
    for col in value_cols[:1]:
        vol_section = generate_volatility_regime(df, col, date_col)
        if vol_section:
            sections.append(vol_section)

    # ========== 7. 风险度量 ==========
    for col in value_cols[:1]:
        risk_section = generate_risk_metrics(df, col, date_col)
        if risk_section:
            sections.append(risk_section)

    # ========== 8. 近期数据 ==========
    sections.append(generate_recent_data(df, date_col, value_cols))

    return "\n\n".join(sections)


def identify_columns(df: pd.DataFrame):
    """识别日期列和数值列"""
    date_col = None
    value_cols = []

    for col in df.columns:
        col_lower = col.lower()
        if col_lower in ['date', 'datetime', 'time', 'timestamp', 'index']:
            date_col = col
        elif df[col].dtype in [np.float64, np.int64, float, int]:
            value_cols.append(col)

    # 如果没找到日期列，尝试第一列
    if date_col is None and len(df.columns) > 0:
        first_col = df.columns[0]
        if df[first_col].dtype == object:
            try:
                pd.to_datetime(df[first_col])
                date_col = first_col
            except:
                pass

    # 如果没找到数值列
    if not value_cols:
        value_cols = [c for c in df.columns if c != date_col]

    return date_col, value_cols


def generate_basic_info(df: pd.DataFrame, date_col: str, value_cols: List[str]) -> str:
    """生成基本信息"""
    lines = []
    lines.append(f"数据点数: {len(df)}")

    if date_col:
        lines.append(f"时间范围: {df[date_col].iloc[0].strftime('%Y-%m-%d')} 至 {df[date_col].iloc[-1].strftime('%Y-%m-%d')}")
        # 计算频率
        if len(df) > 1:
            avg_gap = (df[date_col].iloc[-1] - df[date_col].iloc[0]).days / (len(df) - 1)
            if avg_gap < 2:
                freq = "日度"
            elif avg_gap < 10:
                freq = "周度"
            elif avg_gap < 45:
                freq = "月度"
            elif avg_gap < 120:
                freq = "季度"
            else:
                freq = "年度"
            lines.append(f"数据频率: {freq}")

    lines.append(f"数值列: {', '.join(value_cols[:3])}")

    return "[基本信息]\n" + "\n".join(lines)


def generate_global_stats(df: pd.DataFrame, col: str, date_col: str) -> str:
    """生成全局统计"""
    y = df[col].dropna().values
    if len(y) == 0:
        return ""

    stats = []
    stats.append(f"  起始值: {y[0]:.4g}")
    stats.append(f"  结束值: {y[-1]:.4g}")
    stats.append(f"  最小值: {y.min():.4g}")
    stats.append(f"  最大值: {y.max():.4g}")
    stats.append(f"  均值: {y.mean():.4g}")
    stats.append(f"  中位数: {np.median(y):.4g}")
    stats.append(f"  标准差: {y.std():.4g}")

    # 累计变化
    if y[0] != 0:
        total_change = (y[-1] / y[0] - 1) * 100
        stats.append(f"  累计变化: {total_change:+.2f}%")

    # 收益率统计
    if len(y) > 1:
        returns = np.diff(y) / y[:-1]
        returns = returns[np.isfinite(returns)]
        if len(returns) > 0:
            stats.append(f"  日均收益: {returns.mean()*100:.4f}%")
            stats.append(f"  年化波动率: {returns.std() * np.sqrt(252) * 100:.2f}%")
            stats.append(f"  偏度: {pd.Series(returns).skew():.3f}")
            stats.append(f"  峰度: {pd.Series(returns).kurtosis():.3f}")

    return f"[{col} 全局统计]\n" + "\n".join(stats)


def generate_segment_analysis(df: pd.DataFrame, col: str, date_col: str) -> str:
    """
    使用 pwlf 进行分段分析

    优化策略:
    - 使用 fitfast() 替代 fit()，使用 L-BFGS-B 优化器，速度更快
    - 对于大数据集(>1000)，先下采样再拟合，最后映射回原始索引
    """
    y_orig = df[col].dropna().values
    n_orig = len(y_orig)

    if n_orig < 50:
        return ""

    try:
        import pwlf
    except ImportError:
        return generate_simple_segments(df, col, date_col)

    # 大数据集下采样优化
    DOWNSAMPLE_THRESHOLD = 1000
    if n_orig > DOWNSAMPLE_THRESHOLD:
        # 下采样到约 500 个点
        step = n_orig // 500
        sample_indices = np.arange(0, n_orig, step)
        y = y_orig[sample_indices]
        x = np.arange(len(y))
        is_downsampled = True
    else:
        y = y_orig
        x = np.arange(n_orig)
        sample_indices = np.arange(n_orig)
        is_downsampled = False

    n = len(y)

    try:
        my_pwlf = pwlf.PiecewiseLinFit(x, y)
        n_segments = min(15, max(3, n // 25))  # 每25个点一段，最多15段，至少3段

        # 使用 fitfast() 替代 fit()，速度快10-100倍
        # pop 参数控制优化起点数量，增加可提高精度
        breaks = my_pwlf.fitfast(n_segments, pop=5)
        slopes = my_pwlf.slopes
        r_squared = my_pwlf.r_squared()
    except Exception as e:
        return generate_simple_segments(df, col, date_col)

    lines = []
    method_note = "pwlf 分段线性拟合 (fitfast)"
    if is_downsampled:
        method_note += f" [下采样: {n_orig}→{n}点]"
    lines.append(f"方法: {method_note}")
    lines.append(f"段数: {len(slopes)}, R²={r_squared:.4f}")
    lines.append("")

    for i in range(len(slopes)):
        # 获取下采样空间中的索引
        start_idx_sampled = int(breaks[i])
        end_idx_sampled = int(breaks[i+1]) if i < len(breaks)-1 else n

        if end_idx_sampled > n:
            end_idx_sampled = n

        # 映射回原始索引
        start_idx = sample_indices[min(start_idx_sampled, len(sample_indices)-1)]
        end_idx = sample_indices[min(end_idx_sampled-1, len(sample_indices)-1)] + 1

        if end_idx > n_orig:
            end_idx = n_orig

        seg_y = y_orig[start_idx:end_idx]
        if len(seg_y) < 2:
            continue

        # 判断趋势 (使用下采样空间的斜率)
        slope_normalized = slopes[i] / (y.std() + 1e-10)
        if slope_normalized > 0.01:
            trend = "↗上升"
        elif slope_normalized < -0.01:
            trend = "↘下降"
        else:
            trend = "→横盘"

        # 计算变化幅度
        change_pct = (seg_y[-1] / seg_y[0] - 1) * 100 if seg_y[0] != 0 else 0

        # 日期范围
        if date_col:
            start_date = df[date_col].iloc[start_idx].strftime('%Y-%m-%d')
            end_date = df[date_col].iloc[min(end_idx-1, n_orig-1)].strftime('%Y-%m-%d')
            lines.append(f"  段{i+1}: {start_date}→{end_date} ({end_idx-start_idx}日), {trend}, 变化{change_pct:+.1f}%")
        else:
            lines.append(f"  段{i+1}: 索引{start_idx}-{end_idx}, {trend}, 变化{change_pct:+.1f}%")

    return f"[{col} 分段分析]\n" + "\n".join(lines)


def generate_simple_segments(df: pd.DataFrame, col: str, date_col: str) -> str:
    """简单分段（pwlf不可用时的降级方案）"""
    y = df[col].dropna().values
    n = len(y)

    n_segments = min(5, n // 100)
    if n_segments < 2:
        return ""

    segment_len = n // n_segments
    lines = []
    lines.append(f"方法: 均匀分段 (简化)")
    lines.append("")

    for i in range(n_segments):
        start = i * segment_len
        end = (i + 1) * segment_len if i < n_segments - 1 else n

        seg_y = y[start:end]
        if len(seg_y) < 2:
            continue

        # 计算斜率
        x = np.arange(len(seg_y))
        slope = np.polyfit(x, seg_y, 1)[0]
        normalized_slope = slope / (seg_y.mean() + 1e-10)

        if normalized_slope > 0.001:
            trend = "↗上升"
        elif normalized_slope < -0.001:
            trend = "↘下降"
        else:
            trend = "→横盘"

        change_pct = (seg_y[-1] / seg_y[0] - 1) * 100 if seg_y[0] != 0 else 0

        if date_col:
            start_date = df[date_col].iloc[start].strftime('%Y-%m-%d')
            end_date = df[date_col].iloc[min(end-1, n-1)].strftime('%Y-%m-%d')
            lines.append(f"  段{i+1}: {start_date}→{end_date}, {trend}, 变化{change_pct:+.1f}%")
        else:
            lines.append(f"  段{i+1}: 索引{start}-{end}, {trend}, 变化{change_pct:+.1f}%")

    return f"[{col} 分段分析]\n" + "\n".join(lines)


def generate_changepoints(df: pd.DataFrame, col: str, date_col: str) -> str:
    """变点检测（基于滚动统计量突变）"""
    y = df[col].dropna().values
    n = len(y)

    if n < 100:
        return ""

    window = min(30, n // 10)

    # 计算滚动均值和标准差
    rolling_mean = pd.Series(y).rolling(window).mean().values
    rolling_std = pd.Series(y).rolling(window).std().values

    # 计算变化率
    mean_diff = np.abs(np.diff(rolling_mean[window:]))
    threshold = np.percentile(mean_diff[np.isfinite(mean_diff)], 90)

    # 找到显著变点
    changepoints = []
    for i, diff in enumerate(mean_diff):
        if diff > threshold:
            idx = i + window
            if len(changepoints) == 0 or idx - changepoints[-1]['index'] > window:
                changepoints.append({
                    'index': idx,
                    'value': y[idx],
                    'strength': diff / threshold
                })

    if not changepoints:
        return ""

    # 只取最显著的5个
    changepoints = sorted(changepoints, key=lambda x: x['strength'], reverse=True)[:5]
    changepoints = sorted(changepoints, key=lambda x: x['index'])

    lines = []
    lines.append(f"检测到 {len(changepoints)} 个显著变点:")
    lines.append("")

    for i, cp in enumerate(changepoints):
        if date_col:
            cp_date = df[date_col].iloc[cp['index']].strftime('%Y-%m-%d')
            lines.append(f"  变点{i+1}: {cp_date}, 值={cp['value']:.4g}, 强度={'★'*min(5, int(cp['strength']))}")
        else:
            lines.append(f"  变点{i+1}: 索引{cp['index']}, 值={cp['value']:.4g}")

    return f"[{col} 变点检测]\n" + "\n".join(lines)


def generate_extrema(df: pd.DataFrame, col: str, date_col: str) -> str:
    """极值点检测 (scipy.signal.find_peaks)"""
    y = df[col].dropna().values
    n = len(y)

    if n < 20:
        return ""

    # 参数设置
    prominence_threshold = y.std() * 0.5
    distance = max(1, int(n * 0.02))

    # 检测峰
    peaks, peak_props = find_peaks(y, prominence=prominence_threshold, distance=distance)
    # 检测谷
    troughs, trough_props = find_peaks(-y, prominence=prominence_threshold, distance=distance)

    lines = []
    lines.append(f"参数: prominence={prominence_threshold:.2f}, distance={distance}")
    lines.append(f"检测到: {len(peaks)} 个峰, {len(troughs)} 个谷")
    lines.append("")

    # 全局极值
    max_idx = np.argmax(y)
    min_idx = np.argmin(y)

    if date_col:
        lines.append(f"  全局最高: {y[max_idx]:.4g} ({df[date_col].iloc[max_idx].strftime('%Y-%m-%d')})")
        lines.append(f"  全局最低: {y[min_idx]:.4g} ({df[date_col].iloc[min_idx].strftime('%Y-%m-%d')})")
    else:
        lines.append(f"  全局最高: {y[max_idx]:.4g} (索引{max_idx})")
        lines.append(f"  全局最低: {y[min_idx]:.4g} (索引{min_idx})")

    # Top 3 峰
    if len(peaks) > 0:
        lines.append("")
        lines.append("  显著峰值:")
        sorted_peaks = sorted(zip(peaks, peak_props['prominences']), key=lambda x: x[1], reverse=True)[:3]
        for idx, prom in sorted_peaks:
            if date_col:
                lines.append(f"    - {y[idx]:.4g} ({df[date_col].iloc[idx].strftime('%Y-%m-%d')}), 显著度={prom:.2f}")
            else:
                lines.append(f"    - {y[idx]:.4g} (索引{idx})")

    # Top 3 谷
    if len(troughs) > 0:
        lines.append("")
        lines.append("  显著谷值:")
        sorted_troughs = sorted(zip(troughs, trough_props['prominences']), key=lambda x: x[1], reverse=True)[:3]
        for idx, prom in sorted_troughs:
            if date_col:
                lines.append(f"    - {y[idx]:.4g} ({df[date_col].iloc[idx].strftime('%Y-%m-%d')}), 显著度={prom:.2f}")
            else:
                lines.append(f"    - {y[idx]:.4g} (索引{idx})")

    return f"[{col} 极值点]\n" + "\n".join(lines)


def generate_volatility_regime(df: pd.DataFrame, col: str, date_col: str) -> str:
    """波动体制识别"""
    y = df[col].dropna().values
    n = len(y)

    if n < 100:
        return ""

    window = min(60, n // 5)

    # 计算滚动波动率
    rolling_vol = []
    for i in range(window, n):
        window_data = y[max(0, i-window):i]
        if len(window_data) < 2:
            continue
        returns = np.diff(window_data) / window_data[:-1]
        returns = returns[np.isfinite(returns)]
        if len(returns) > 0:
            vol = returns.std() * np.sqrt(252) * 100
            rolling_vol.append(vol)

    if len(rolling_vol) < 10:
        return ""

    rolling_vol = np.array(rolling_vol)

    # 分位数阈值
    q33 = np.percentile(rolling_vol, 33)
    q66 = np.percentile(rolling_vol, 66)

    # 识别体制
    regimes = []
    current_regime = None
    regime_start = window

    for i, vol in enumerate(rolling_vol):
        if vol < q33:
            regime = '低波动'
        elif vol < q66:
            regime = '中波动'
        else:
            regime = '高波动'

        if regime != current_regime:
            if current_regime is not None:
                regimes.append({
                    'regime': current_regime,
                    'start_idx': regime_start,
                    'end_idx': window + i - 1,
                    'avg_vol': rolling_vol[regime_start-window:i].mean() if regime_start >= window else rolling_vol[:i].mean()
                })
            current_regime = regime
            regime_start = window + i

    # 添加最后一个体制
    if current_regime is not None:
        regimes.append({
            'regime': current_regime,
            'start_idx': regime_start,
            'end_idx': n - 1,
            'avg_vol': rolling_vol[regime_start-window:].mean() if regime_start >= window else rolling_vol.mean()
        })

    if not regimes:
        return ""

    lines = []
    lines.append(f"阈值: 低<{q33:.1f}%, 中{q33:.1f}-{q66:.1f}%, 高>{q66:.1f}%")
    lines.append(f"识别到 {len(regimes)} 个体制:")
    lines.append("")

    # 只显示主要的几个体制
    for r in regimes[-5:]:
        emoji = '📉' if r['regime'] == '低波动' else '📊' if r['regime'] == '中波动' else '📈'
        if date_col:
            start_date = df[date_col].iloc[min(r['start_idx'], n-1)].strftime('%Y-%m-%d')
            end_date = df[date_col].iloc[min(r['end_idx'], n-1)].strftime('%Y-%m-%d')
            lines.append(f"  {emoji} {start_date}→{end_date}: {r['regime']} (平均{r['avg_vol']:.1f}%)")
        else:
            lines.append(f"  {emoji} 索引{r['start_idx']}-{r['end_idx']}: {r['regime']}")

    return f"[{col} 波动体制]\n" + "\n".join(lines)


def generate_risk_metrics(df: pd.DataFrame, col: str, date_col: str) -> str:
    """风险度量"""
    y = df[col].dropna().values
    n = len(y)

    if n < 10:
        return ""

    lines = []

    # 最大回撤
    cummax = np.maximum.accumulate(y)
    drawdown = (y - cummax) / cummax
    max_dd_idx = np.argmin(drawdown)
    max_dd = drawdown[max_dd_idx]
    dd_start_idx = np.argmax(y[:max_dd_idx+1]) if max_dd_idx > 0 else 0

    if date_col:
        lines.append(f"  最大回撤: {max_dd*100:.2f}%")
        lines.append(f"    起点: {df[date_col].iloc[dd_start_idx].strftime('%Y-%m-%d')} (值={y[dd_start_idx]:.4g})")
        lines.append(f"    终点: {df[date_col].iloc[max_dd_idx].strftime('%Y-%m-%d')} (值={y[max_dd_idx]:.4g})")
        lines.append(f"    持续: {max_dd_idx - dd_start_idx} 天")
    else:
        lines.append(f"  最大回撤: {max_dd*100:.2f}% (索引{dd_start_idx}→{max_dd_idx})")

    # 最长连跌
    if n > 1:
        returns = np.diff(y) / y[:-1]
        losing_streak = 0
        max_losing_streak = 0
        max_streak_end = 0

        for i, r in enumerate(returns):
            if r < 0:
                losing_streak += 1
                if losing_streak > max_losing_streak:
                    max_losing_streak = losing_streak
                    max_streak_end = i + 1
            else:
                losing_streak = 0

        lines.append(f"  最长连跌: {max_losing_streak} 天")
        if max_streak_end > 0 and date_col:
            lines.append(f"    结束于: {df[date_col].iloc[max_streak_end].strftime('%Y-%m-%d')}")

    return f"[{col} 风险度量]\n" + "\n".join(lines)


def generate_recent_data(df: pd.DataFrame, date_col: str, value_cols: List[str]) -> str:
    """生成近期数据"""
    recent_n = min(10, len(df))
    recent_df = df.tail(recent_n)

    if date_col:
        cols = [date_col] + value_cols[:3]
    else:
        cols = value_cols[:3]

    cols = [c for c in cols if c in df.columns]
    recent_data = recent_df[cols].to_string(index=False)

    return f"[近期数据 - 最后{recent_n}条]\n{recent_data}"
