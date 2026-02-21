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
import cv2
from loguru import logger
from pathlib import Path

import numpy as np

# 全局图片存储目录（由 setup_logger 设置）
_image_dir: Path | None = None

# 项目根目录，用于将绝对路径转换为相对路径（Ctrl+点击用）
_PROJECT_ROOT = Path(__file__).parent.parent


def _src_patcher(record: dict) -> None:
    """将 record["file"].path 转为以项目根目录为基准的相对路径，并存入 extra["src"]。

    格式示例：``autowsgr/emulator/controller.py:346``
    在 VS Code 终端中可通过 Ctrl+点击直接跳转。
    """
    try:
        rel = Path(record["file"].path).relative_to(_PROJECT_ROOT)
        # 统一使用正斜杠，与 VS Code 兼容
        record["extra"]["src"] = f"{rel.as_posix()}:{record['line']}"
    except ValueError:
        record["extra"]["src"] = f"{record['file'].name}:{record['line']}"


def setup_logger(
    log_dir: Path | None = None,
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
    save_images: bool = False,
    show_pixel_detail: bool = False,
    show_image_detail: bool = False,
    show_screenshot_detail: bool = False,
) -> None:
    """配置全局 loguru logger。

    日志策略：
    - 控制台：按 *level* 过滤输出。
    - 文件（全量）：始终以 DEBUG 级别记录，文件名含 ``.debug`` 后缀，不可通过参数更改级别。
    - 文件（过滤）：与控制台 *level* 一致，文件名不含后缀。

    Parameters
    ----------
    log_dir:
        日志文件存放目录。为 *None* 时仅输出到控制台。
    level:
        控制台及过滤文件的最低日志级别。
    rotation:
        单个日志文件最大体积或时间周期。
    retention:
        日志文件保留时长。
    save_images:
        是否开启截图自动保存（保存至 log_dir/images/）。
    show_pixel_detail:
        是否输出逐像素规则匹配的 DEBUG 日志（期望/实际/距离等）。
        默认 ``False``，仅输出签名级别的结果。
    show_image_detail:
        是否输出逐模板匹配的 DEBUG 日志（置信度/坐标等）。
        默认 ``False``，仅输出签名级别的结果。
    show_screenshot_detail:
        是否输出每次截图的完成日志（尺寸/耗时）。
        默认 ``False``，避免在 DEBUG 模式下刷屏。
    """
    global _image_dir

    # 同步像素检测细节日志开关
    from autowsgr.vision.matcher import configure as _configure_matcher
    _configure_matcher(show_pixel_detail=show_pixel_detail)

    # 同步图像模板匹配细节日志开关
    from autowsgr.vision.image_matcher import configure as _configure_image_matcher
    _configure_image_matcher(show_image_detail=show_image_detail)

    # 同步截图完成细节日志开关
    from autowsgr.emulator.controller import configure as _configure_controller
    _configure_controller(show_screenshot_detail=show_screenshot_detail)

    # 移除默认 handler，避免重复输出
    logger.remove()

    # 注册 patcher：为每条记录附加可点击的相对路径
    logger.configure(patcher=_src_patcher)

    _FMT = (
        "<green>{time:HH:mm:ss.SSS}</green> | "
        "<level>{level:8}</level> | "
        "<cyan>{extra[src]}</cyan> | "
        "{message}"
    )

    # 控制台输出（按 level 过滤）
    logger.add(
        sys.stderr,
        level=level,
        format=_FMT,
    )

    # 文件输出
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)

        # 全量文件：固定 DEBUG 级别，不可配置
        logger.add(
            log_dir / "autowsgr_{time:YYYY-MM-DD}.debug.log",
            level="DEBUG",
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
            format=_FMT,
        )

        # 过滤文件：与控制台 level 一致
        if level.upper() != "DEBUG":
            logger.add(
                log_dir / "autowsgr_{time:YYYY-MM-DD}.log",
                level=level,
                rotation=rotation,
                retention=retention,
                encoding="utf-8",
                format=_FMT,
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
