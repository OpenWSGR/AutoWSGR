"""分析 overlay 数据集: 通用方案判断 click 是否触发均匀半透明黑罩浮层。

通用方案 (ratio clustering + 拓扑, 无需预知浮窗边界/形状):
  均匀半透明黑罩的物理本质是**乘性压暗**: after ≈ before x t (t<1)。浮层的几何结构是
  **外围(底层页)被均匀压暗 + 中心(浮窗面板)不被压暗**。据此:
    1. ratio clustering: 全页 after/before 比值找众数 t (压暗系数, 自适应不同浮层不透明度)。
    2. 用 t unmask 整页, 算 per-pixel diff, 标记"匹配像素"(diff<3, 即被精确还原者)。
    3. 拓扑判定 (核心, 不要求形状规则, 只要求拓扑):
       - 最外 1 像素匹配率高 (outer): 任何浮窗都有边距, 最外圈必然是未被覆盖的底层页 →
         被均匀压暗则 unmask 后精确还原。
       - 外圈匹配 > 中心 (edge > center): 环形包围结构 (外围=底层页匹配, 中心=面板不匹配)。
  这组参数同时适用大浮窗 (bath, 仅边缘 11% 未遮) 和小浮窗 (确认弹窗, 71% 未遮),
  且能区分"打开浮层"(外围匹配/中心不匹配) 与 "关闭浮层"(外围不匹配/中心匹配) —— 后者
  面板位置可能巧合呈乘性, 但拓扑相反, 纯占比方案无法区分。

判定 (通用, 阈值均基于物理/拓扑意义, 非逐浮层调参):
  - 无变化:     全页平均 diff < 5
  - 均匀蒙版 ★: t∈(0,0.55) 且 outer>10% 且 edge>center
  - 不适用:     无外围压暗拓扑 (页跳转/亮色面板/关闭浮层)

用法:
    uv run python examples/analyze_overlay.py path/to/overlay_dataset/{timestamp}
    uv run python examples/analyze_overlay.py <dataset> --bands=20,20,25,20   # 对照
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

from autowsgr.vision import OverlayChecker
from autowsgr.vision.overlay import DARKEN_TOL, NOCHANGE_GLOBAL


# 算法常量与检测逻辑已提炼至 autowsgr.vision.overlay (OverlayChecker); 本文件
# 保留 CLI/报告输出 + --bands 边缘通道比对照, 作为单一真相源之上的分析工具。


def load_rgb(path: Path) -> np.ndarray:
    bgr = cv2.imread(str(path))
    if bgr is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def edge_mask(
    h: int, w: int, center_frac: float = 0.4, bands: tuple[int, int, int, int] | None = None
) -> np.ndarray:
    """边缘 mask, 仅 --bands 对照模式用。"""
    if bands is not None:
        left, right, top, bottom = bands
        m = np.zeros((h, w), bool)
        if left:
            m[:, :left] = True
        if right:
            m[:, w - right :] = True
        if top:
            m[:top, :] = True
        if bottom:
            m[h - bottom :, :] = True
        return m
    m = np.ones((h, w), bool)
    c = center_frac / 2
    m[int((0.5 - c) * h) : int((0.5 + c) * h), int((0.5 - c) * w) : int((0.5 + c) * w)] = False
    return m


def channel_ratio(before: np.ndarray, after: np.ndarray, mask: np.ndarray) -> list[float]:
    """mask 区三通道 after/before 比值 median (仅 before>10)。仅 mask 模式辅助。"""
    b = before[mask].astype(np.float32)
    a = after[mask].astype(np.float32)
    ratios: list[float] = []
    for c in range(3):
        bc, ac = b[:, c], a[:, c]
        valid = bc > 10
        ratios.append(float(np.median(ac[valid] / bc[valid])) if valid.any() else float('nan'))
    return ratios


def analyze_click(
    before: np.ndarray, after: np.ndarray, mask: np.ndarray | None = None, tol: float = DARKEN_TOL
) -> dict:
    """判断 click 是否触发均匀蒙版浮层 (调 :func:`OverlayChecker.detect_uniform_mask`)。

    mask 给定时额外报告边缘通道比 cv (--bands 对照, 不影响判定)。
    """
    result = OverlayChecker.detect_uniform_mask(before, after, tol=tol)
    if result.matched:
        verdict = '均匀蒙版 (拓扑: 外围还原+环形包围) ★'
    elif result.raw_diff < NOCHANGE_GLOBAL:
        verdict = '无变化 (前后几乎未变)'
    else:
        verdict = '不适用 (无外围压暗拓扑: 页跳转/亮色面板/关闭浮层)'
    out: dict = {
        'raw_global': round(result.raw_diff, 2),
        'darken_factor': result.darken_factor,
        'outer_pct': round(result.outer_frac * 100, 1),
        'edge_pct': round(result.edge_frac * 100, 1),
        'center_pct': round(result.center_frac * 100, 1),
        'verdict': verdict,
    }
    if mask is not None:
        ratios = channel_ratio(before, after, mask)
        rm = float(np.nanmean(ratios))
        out['ratio_cv'] = round(float(np.nanstd(ratios) / abs(rm)) if rm else float('nan'), 3)
    return out


def main() -> None:
    positional = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if not positional:
        print('用法: uv run python examples/analyze_overlay.py <dataset_dir> [--bands=L,R,T,B]')
        print('  默认: 通用 ratio clustering (无需浮窗边界, 适用所有均匀蒙版浮层)')
        print('  --bands: 仅对照, 额外报告边缘通道比 cv (不影响判定)')
        sys.exit(1)
    data_dir = Path(positional[0])
    bands = None
    for f in flags:
        if f.startswith('--bands='):
            bands = tuple(int(x) for x in f.split('=', 1)[1].split(','))
    manifest_path = data_dir / 'manifest.yaml'
    if not manifest_path.exists():
        print(f'找不到 manifest: {manifest_path}')
        sys.exit(1)
    with open(manifest_path, encoding='utf-8') as f:
        manifest = yaml.safe_load(f)
    clicks = manifest.get('clicks', [])
    print(f'数据集: {data_dir}')
    print(
        f'模式: 通用 ratio clustering (tol={DARKEN_TOL})'
        + (f' + 对照 bands={bands}' if bands else '')
    )
    print(f'click 数: {len(clicks)}\n')

    first = cv2.imread(str(data_dir / 'click_0001_before.png'))
    if first is None:
        print('找不到 click_0001_before.png')
        sys.exit(1)
    mask = edge_mask(first.shape[0], first.shape[1], bands=bands) if bands else None

    results = []
    pairs = []  # (idx, before, after) 缓存, 容差敏感性测试用
    counts: dict[str, int] = {}
    for entry in clicks:
        idx = entry['idx']
        bp, ap = data_dir / f'click_{idx:04d}_before.png', data_dir / f'click_{idx:04d}_after.png'
        if not (bp.exists() and ap.exists()):
            continue
        before, after = load_rgb(bp), load_rgb(ap)
        pairs.append((idx, before, after))
        m = analyze_click(before, after, mask=mask)
        chain = entry.get('caller_chain') or []
        caller = chain[-1] if chain else '?'
        m.update(idx=idx, method=entry.get('method'), caller=caller)
        results.append(m)
        counts[m['verdict']] = counts.get(m['verdict'], 0) + 1
        cv = f' cv={m["ratio_cv"]:.3f}' if 'ratio_cv' in m else ''
        print(
            f'[{idx:04d}] {m["verdict"]:38s} raw={m["raw_global"]:5.1f} '
            f't={m["darken_factor"]:.3f} outer={m["outer_pct"]:4.1f}% '
            f'edge/ctr={m["edge_pct"]:4.1f}/{m["center_pct"]:4.1f}%{cv}  <- {caller}'
        )

    print('\n=== 统计 ===')
    for v, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f'  {n:3d}  {v}')

    # 通用性验证: 容差敏感性 —— ★ 数跨容差稳定 = 方案通用, 非特定容差过拟合
    if pairs:
        print('\n=== 容差敏感性 (通用性验证: ★ 数应跨容差稳定) ===')
        for tol in [0.03, 0.04, 0.05, 0.06]:
            stars = sum(
                1 for _, b, a in pairs if OverlayChecker.detect_uniform_mask(b, a, tol=tol).matched
            )
            mark = ' (当前)' if abs(tol - DARKEN_TOL) < 1e-6 else ''
            print(f'  tol={tol:.2f}{mark}: ★={stars}/{len(pairs)}')

    out = data_dir / 'analysis.yaml'
    with open(out, 'w', encoding='utf-8') as f:
        yaml.safe_dump(
            {'mode': 'ratio_clustering', 'tol': DARKEN_TOL, 'counts': counts, 'clicks': results},
            f,
            allow_unicode=True,
            sort_keys=False,
            width=200,
        )
    print(f'\n报告 -> {out}')


if __name__ == '__main__':
    main()
