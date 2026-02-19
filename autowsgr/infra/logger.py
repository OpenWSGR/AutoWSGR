"""全局日志配置。

使用方式::

    # 应用启动时调用一次
    from autowsgr.infra.logger import setup_logger
    setup_logger(log_dir=Path("log/2026-01-01"))

    # 各模块直接使用 loguru
    from loguru import logger
    logger.info("开始出征 章节={} 地图={}", chapter, map_id)

    # 保存截图到日志目录
    from autowsgr.infra.logger import save_image
    save_image(screen, tag="click_before")
"""

from __future__ import annotations

import logging
import sys
import time as _time
from pathlib import Path

import numpy as np

# 全局图片存储目录（由 setup_logger 设置）
_image_dir: Path | None = None


def setup_logger(
    log_dir: Path | None = None,
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
    save_images: bool = False,
) -> None:
    """配置全局 loguru logger。

    Parameters
    ----------
    log_dir:
        日志文件存放目录。为 *None* 时仅输出到控制台。
    level:
        最低日志级别。
    rotation:
        单个日志文件最大体积或时间周期。
    retention:
        日志文件保留时长。
    save_images:
        是否开启截图自动保存（保存至 log_dir/images/）。
    """
    global _image_dir
    from loguru import logger

    # 移除默认 handler，避免重复输出
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level:8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
    )

    # 文件输出
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "autowsgr_{time:YYYY-MM-DD}.log",
            level=level,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
        )

        # 图片目录
        if save_images:
            _image_dir = log_dir / "images"
            _image_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("截图存储目录: {}", _image_dir)
    else:
        _image_dir = None

    # ── 静默第三方库的 Python logging 噪音 ──────────────────────────────
    # airtest 使用标准 logging 模块，默认输出大量 DEBUG 行；统一压到 WARNING
    for _noisy in (
        "airtest",
        "airtest.core.android.adb",
        "airtest.core.android.rotation",
        "airtest.utils.nbsp",
        "pocoui",
    ):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


def save_image(
    image: np.ndarray,
    tag: str = "screenshot",
    img_dir: Path | None = None,
) -> Path | None:
    """将 RGB ndarray 截图保存到磁盘。

    Parameters
    ----------
    image:
        RGB uint8 数组 (H×W×3)。
    tag:
        文件名前缀（不含扩展名）。
    img_dir:
        目标目录。为 *None* 时使用 :func:`setup_logger` 中设定的全局目录；
        全局目录也为 None 则直接返回 None（不保存）。

    Returns
    -------
    Path | None
        保存的文件路径，未保存时返回 None。
    """
    import cv2
    from loguru import logger

    target_dir = img_dir or _image_dir
    if target_dir is None:
        return None

    target_dir.mkdir(parents=True, exist_ok=True)
    ts = _time.strftime("%H%M%S") + f"_{int(_time.monotonic() * 1000) % 1000:03d}"
    filename = f"{tag}_{ts}.png"
    path = target_dir / filename

    # cv2.imwrite 期望 BGR 排列，而我们统一使用 RGB，写入前需转换
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    # 使用 imencode + write_bytes 避免 OpenCV C 层 ANSI 路径导致中文乱码
    ok, buf = cv2.imencode(".png", bgr)
    if ok:
        path.write_bytes(buf.tobytes())
        logger.debug("截图已保存: {}", path)
    else:
        logger.warning("截图保存失败: {}", path)
        return None
    return path
