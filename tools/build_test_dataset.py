"""从 smoke_walk 截图生成严格的页面识别测试数据集。

用法::

    python tools/build_test_dataset.py

输入:
    logs/smoke_walk/images/*.png  — UI 游走截图 (含文件名中的动作描述)

输出:
    logs/testing/
        manifest.json              — 完整数据清单 (标签 + 路径)
        {页面标签}/
            orig_{序号}.png        — 原始截图 (保持原始分辨率)
            r1600x900_{序号}.png   — 缩放到 1600×900
            r1366x768_{序号}.png   — 缩放到 1366×768
            s{dx:+d}{dy:+d}_{序号}.png  — 1600×900 + 像素偏移

数据增强策略:
    1. 每个页面最多保留 4 张原始截图 (优先选择不同 tab/panel 的多样性)
    2. 每张原始图生成:
       - 2 种额外分辨率 (1600×900, 1366×768)
       - 在 1600×900 基础上做 8 个方向的 ±1px 偏移
    3. 排除 _error 后缀的截图 (导航失败, 页面不确定)
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import cv2
import numpy as np

# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════

SRC_DIR = Path("logs/smoke_walk/images")
DST_DIR = Path("logs/testing")

MAX_PER_PAGE = 4  # 每个页面最多保留的原始截图数

# 增强分辨率
AUG_RESOLUTIONS: list[tuple[int, int]] = [
    (1600, 900),
    (1366, 768),
]

# 像素偏移: 在 1600×900 上做 ±1 px
SHIFTS: list[tuple[int, int]] = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

# 时间戳模式: 6位数字_3位数字 (如 010415_064)
_TS_RE = re.compile(r"_(\d{6}_\d{3})$")


# ═══════════════════════════════════════════════════════════════════════════════
# 文件名解析 → 页面标签
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_filename(stem: str) -> tuple[str, str, str] | None:
    """解析文件名, 返回 (page_label, sub_label, step_id) 或 None (跳过).

    文件名格式: {step:03d}_{description}_{timestamp}
    """
    # 跳过 error 截图
    if "_error" in stem:
        return None

    # 去掉时间戳
    m = _TS_RE.search(stem)
    if not m:
        return None
    desc_part = stem[: m.start()]  # e.g. "002_主页面_to_地图页面_(出征)"

    # 去掉步骤序号前缀
    parts = desc_part.split("_", 1)
    if len(parts) < 2:
        return None
    step_id = parts[0]  # "002"
    desc = parts[1]  # "主页面_to_地图页面_(出征)"

    # ── 模式匹配 ──

    # 1. verify_X
    if desc.startswith("verify_"):
        page = desc[len("verify_") :]
        return page, "", step_id

    # 2. X_切换面板_to_Z  → page=X, sub=Z
    m2 = re.match(r"(.+?)_切换面板_to_(.+)", desc)
    if m2:
        return m2.group(1), f"面板_{m2.group(2)}", step_id

    # 3. X_切换标签_to_Z  → page=X, sub=Z
    m2 = re.match(r"(.+?)_切换标签_to_(.+)", desc)
    if m2:
        return m2.group(1), f"标签_{m2.group(2)}", step_id

    # 4. X_to_close_to_Y  → page=Y
    m2 = re.match(r".+_to_close_to_(.+)", desc)
    if m2:
        return m2.group(1), "", step_id

    # 5. X_to_back_Y  → page=Y
    m2 = re.match(r".+_to_back_(.+)", desc)
    if m2:
        return m2.group(1), "", step_id

    # 6. X_to_Y (可能带括号后缀)  → page=Y
    m2 = re.match(r".+_to_(.+)", desc)
    if m2:
        raw_target = m2.group(1)
        # 去掉括号信息 如 "地图页面_(出征)" → "地图页面", sub="出征"
        m3 = re.match(r"(.+?)_\((.+?)\)", raw_target)
        if m3:
            return m3.group(1), m3.group(2), step_id
        return raw_target, "", step_id

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 图像操作
# ═══════════════════════════════════════════════════════════════════════════════


def _load_image(path: Path) -> np.ndarray:
    """读取图像 (BGR)."""
    buf = np.frombuffer(path.read_bytes(), np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图像: {path}")
    return img


def _resize(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """缩放图像到指定分辨率."""
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def _shift(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """像素平移, 边缘用最近像素填充 (replicate)."""
    h, w = img.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)


def _save_image(img: np.ndarray, path: Path) -> None:
    """保存图像 (支持中文路径)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError(f"图像编码失败: {path}")
    path.write_bytes(buf.tobytes())


# ═══════════════════════════════════════════════════════════════════════════════
# 样本选择: 多样性优先
# ═══════════════════════════════════════════════════════════════════════════════


def _select_diverse(
    items: list[tuple[Path, str, str, str]],  # (path, page, sub, step)
    max_count: int,
) -> list[tuple[Path, str, str, str]]:
    """从同一页面的多个截图中选择多样性最大的子集.

    优先选择不同 sub_label 的图像, 然后不同分辨率.
    """
    if len(items) <= max_count:
        return items

    selected: list[tuple[Path, str, str, str]] = []
    seen_subs: set[str] = set()

    # 第一轮: 每个不同的 sub_label 各选一个
    for item in items:
        sub = item[2]
        if sub not in seen_subs and len(selected) < max_count:
            selected.append(item)
            seen_subs.add(sub)

    # 第二轮: 如果还不够, 补充不同分辨率的
    if len(selected) < max_count:
        seen_paths = {s[0] for s in selected}
        # 按分辨率分组
        res_groups: dict[tuple[int, int], list[tuple[Path, str, str, str]]] = {}
        for item in items:
            if item[0] in seen_paths:
                continue
            img = _load_image(item[0])
            h, w = img.shape[:2]
            res_groups.setdefault((w, h), []).append(item)

        for _res, group in res_groups.items():
            for item in group:
                if len(selected) >= max_count:
                    break
                if item[0] not in seen_paths:
                    selected.append(item)
                    seen_paths.add(item[0])

    return selected[:max_count]


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    if not SRC_DIR.exists():
        print(f"错误: 源目录不存在: {SRC_DIR}")
        return

    # ── 1. 解析所有文件名 ──
    all_images = sorted(SRC_DIR.glob("*.png"))
    parsed: list[tuple[Path, str, str, str]] = []   # (path, page, sub, step)
    skipped: list[str] = []

    for img_path in all_images:
        result = _parse_filename(img_path.stem)
        if result is None:
            skipped.append(img_path.name)
            continue
        page, sub, step = result
        parsed.append((img_path, page, sub, step))

    # 统计
    page_groups: dict[str, list[tuple[Path, str, str, str]]] = {}
    for item in parsed:
        page_groups.setdefault(item[1], []).append(item)

    print(f"总截图: {len(all_images)}  已解析: {len(parsed)}  已跳过: {len(skipped)}")
    print(f"页面类别: {len(page_groups)}")
    for page, items in sorted(page_groups.items()):
        subs = {it[2] for it in items if it[2]}
        sub_info = f"  子标签: {', '.join(sorted(subs))}" if subs else ""
        print(f"  {page}: {len(items)} 张{sub_info}")

    if skipped:
        print(f"\n跳过的文件 (error 等):")
        for name in skipped:
            print(f"  - {name}")

    # ── 2. 每个子标签独立限制 ≤ MAX_PER_PAGE 张 ──
    #    同一页面的不同子标签 (面板/标签) 各自最多保留 MAX_PER_PAGE 张,
    #    不同子标签之间的配额互不叠加。
    selected: dict[str, list[tuple[Path, str, str, str]]] = {}
    for page, items in page_groups.items():
        # 按子标签分组
        sub_groups: dict[str, list[tuple[Path, str, str, str]]] = {}
        for item in items:
            sub_groups.setdefault(item[2], []).append(item)

        page_selected: list[tuple[Path, str, str, str]] = []
        for sub_label, sub_items in sorted(sub_groups.items()):
            # 每个子标签独立限制 MAX_PER_PAGE
            chosen = sub_items[:MAX_PER_PAGE]
            page_selected.extend(chosen)

        selected[page] = page_selected

    print(f"\n选择后:")
    for page, items in sorted(selected.items()):
        # 按子标签统计
        sub_counts: dict[str, int] = {}
        for it in items:
            key = it[2] or "(无)"
            sub_counts[key] = sub_counts.get(key, 0) + 1
        detail = ", ".join(f"{k}:{v}" for k, v in sorted(sub_counts.items()))
        print(f"  {page}: {len(items)} 张  [{detail}]")

    # ── 3. 清理输出目录 ──
    if DST_DIR.exists():
        shutil.rmtree(DST_DIR)
    DST_DIR.mkdir(parents=True, exist_ok=True)

    # ── 4. 生成数据集 ──
    manifest: list[dict] = []
    total_generated = 0

    for page, items in sorted(selected.items()):
        page_dir = DST_DIR / page
        page_dir.mkdir(parents=True, exist_ok=True)

        for idx, (src_path, _page, sub, step) in enumerate(items):
            img = _load_image(src_path)
            h_orig, w_orig = img.shape[:2]
            base_tag = f"{idx:02d}"

            # (a) 原始分辨率
            orig_name = f"orig_{base_tag}.png"
            _save_image(img, page_dir / orig_name)
            manifest.append({
                "file": f"{page}/{orig_name}",
                "page": page,
                "sub_label": sub,
                "source": src_path.name,
                "resolution": f"{w_orig}x{h_orig}",
                "augmentation": "none",
                "shift": [0, 0],
            })
            total_generated += 1

            # (b) 缩放到其他分辨率
            for res_w, res_h in AUG_RESOLUTIONS:
                if (res_w, res_h) == (w_orig, h_orig):
                    continue  # 跳过与原始相同的分辨率
                resized = _resize(img, res_w, res_h)
                res_name = f"r{res_w}x{res_h}_{base_tag}.png"
                _save_image(resized, page_dir / res_name)
                manifest.append({
                    "file": f"{page}/{res_name}",
                    "page": page,
                    "sub_label": sub,
                    "source": src_path.name,
                    "resolution": f"{res_w}x{res_h}",
                    "augmentation": "resize",
                    "shift": [0, 0],
                })
                total_generated += 1

            # (c) 在 1600×900 上做像素偏移
            base_1600 = _resize(img, 1600, 900)
            for dx, dy in SHIFTS:
                shifted = _shift(base_1600, dx, dy)
                shift_name = f"s{dx:+d}{dy:+d}_{base_tag}.png"
                _save_image(shifted, page_dir / shift_name)
                manifest.append({
                    "file": f"{page}/{shift_name}",
                    "page": page,
                    "sub_label": sub,
                    "source": src_path.name,
                    "resolution": "1600x900",
                    "augmentation": "shift",
                    "shift": [dx, dy],
                })
                total_generated += 1

    # ── 5. 保存清单 ──
    manifest_path = DST_DIR / "manifest.json"
    manifest_data = {
        "description": "AutoWSGR 页面识别测试数据集",
        "source": str(SRC_DIR),
        "max_per_page": MAX_PER_PAGE,
        "aug_resolutions": [f"{w}x{h}" for w, h in AUG_RESOLUTIONS],
        "shifts": SHIFTS,
        "total_images": total_generated,
        "pages": {
            page: {
                "original_count": len(items),
                "total_count": sum(1 for m in manifest if m["page"] == page),
            }
            for page, items in sorted(selected.items())
        },
        "items": manifest,
    }
    manifest_path.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── 6. 汇总 ──
    print(f"\n{'═' * 60}")
    print(f"  数据集生成完成")
    print(f"{'═' * 60}")
    print(f"  输出目录: {DST_DIR.resolve()}")
    print(f"  总图像数: {total_generated}")
    print(f"  清单文件: {manifest_path.resolve()}")
    print()
    for page, items in sorted(selected.items()):
        page_total = sum(1 for m in manifest if m["page"] == page)
        print(f"  {page:12s}: {len(items)} 原始 → {page_total} 增强")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
