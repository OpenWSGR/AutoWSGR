"""全局日志配置 — 基于 loguru 的通道过滤系统。

核心概念
--------
每个业务模块拥有一个 **通道 (channel)** 标识，通过 ``logger.bind(ch="通道名")``
创建模块级 logger。通道使用层级命名 (如 ``"combat.recognition"``)，
支持前缀匹配实现子系统级别过滤。

通道体系
--------
::

    emulator          — 设备操作 (click/swipe/screenshot/key)
    vision.pixel      — 像素特征匹配 (逐规则 detail)
    vision.image      — 模板图像匹配 (逐模板 detail)
    vision.ocr        — OCR 文字识别
    vision.dll        — DLL 调用
    ui                — 页面导航 / 浮层 / 通用 UI 操作
    ui.preparation    — 出征准备页 (血量/换船/补给)
    ui.decisive       — 决战专属 UI (编成/OCR/地图控制器)
    combat            — 战斗引擎 / 状态处理器 / 操作
    combat.recognition — 战斗状态识别 / 敌方编成识别 / 规则
    combat.tracker    — 节点追踪器
    ops               — 常规战/战役/演习/修理/建造
    ops.startup       — 启动流程
    ops.decisive      — 决战调度

使用方式::

    # 应用启动时调用一次
    from autowsgr.infra.logger import setup_logger
    setup_logger(
        log_dir=Path("log/2026-01-01"),
        channels={
            "vision.pixel": "TRACE",   # 开启像素匹配逐条输出
            "emulator": "INFO",        # 屏蔽 click/swipe 的 DEBUG
        },
    )

    # 各模块创建通道 logger
    from autowsgr.infra.logger import get_logger
    _log = get_logger("combat")
    _log.info("战斗结束: {} (节点数={})", result.flag, count)

    # 带调用者追踪的底层接口
    from autowsgr.infra.logger import caller_info
    _log.debug("[Emulator] click({:.3f}, {:.3f})  {}", x, y, caller_info())
"""

# TODO: 自定义图片保存路径

from __future__ import annotations

import inspect
import logging
import sys
import time as _time
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
from loguru import logger


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np


# ═══════════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

# 全局图片存储目录（由 setup_logger 设置）
_image_dir = 'logs/images'

# 项目根目录，用于将绝对路径转换为相对路径（Ctrl+点击用）
_PROJECT_ROOT = Path(__file__).parent.parent

# loguru 内置级别名 → 数值 (用于通道过滤)
_LEVEL_MAP: dict[str, int] = {
    'TRACE': 5,
    'DEBUG': 10,
    'INFO': 20,
    'SUCCESS': 25,
    'WARNING': 30,
    'ERROR': 40,
    'CRITICAL': 50,
}

# 默认通道级别：未在 channels 中指定的通道使用此值。
# 设为 None 表示"跟随 sink 自身级别"（不做额外过滤）。
_DEFAULT_CHANNEL_LEVEL: int | None = None

# 当前通道过滤配置 (由 setup_logger 设置)
_channel_levels: dict[str, int] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# Patcher
# ═══════════════════════════════════════════════════════════════════════════════


def _src_patcher(record: dict) -> None:
    """将 record["file"].path 转为以项目根目录为基准的相对路径，并存入 extra["src"]。

    格式示例：``emulator/controller.py:346``
    在 VS Code 终端中可通过 Ctrl+点击直接跳转。
    """
    try:
        rel = Path(record['file'].path).relative_to(_PROJECT_ROOT)
        # 统一使用正斜杠，与 VS Code 兼容
        record['extra']['src'] = f'{rel.as_posix()}:{record["line"]}'
    except ValueError:
        record['extra']['src'] = f'{record["file"].name}:{record["line"]}'

    # 确保 ch 总是存在（未 bind 的 logger 调用不会有 ch）
    record['extra'].setdefault('ch', '')


# ═══════════════════════════════════════════════════════════════════════════════
# 通道过滤
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_channel_level(channel: str) -> int | None:
    """解析通道的有效级别。

    查找顺序：精确匹配 → 前缀匹配（从最长前缀开始） → 默认值。

    Examples
    --------
    配置 ``{"vision": 30}`` 时：
    - ``"vision.pixel"`` → 30 (前缀匹配 ``"vision"``)
    - ``"vision"`` → 30 (精确匹配)
    - ``"combat"`` → None (默认，跟随 sink 级别)
    """
    if not _channel_levels:
        return _DEFAULT_CHANNEL_LEVEL

    # 精确匹配
    if channel in _channel_levels:
        return _channel_levels[channel]

    # 前缀匹配 (从最长的开始)
    best_prefix = ''
    best_level: int | None = _DEFAULT_CHANNEL_LEVEL
    for prefix, level in _channel_levels.items():
        if channel.startswith(prefix + '.') and len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_level = level
    return best_level


def _make_channel_filter(sink_level: int) -> Callable:
    """创建通道感知的日志过滤函数。

    返回的 filter 函数同时检查：
    1. 消息级别 >= sink 自身级别  (基础过滤)
    2. 消息级别 >= 通道指定级别  (通道过滤)

    无通道 (ch="") 的消息仅检查 sink 级别。
    """

    def _filter(record: dict) -> bool:
        msg_level = record['level'].no
        if msg_level < sink_level:
            return False

        channel = record['extra'].get('ch', '')
        if not channel:
            return True  # 无通道的消息不做额外过滤

        ch_level = _resolve_channel_level(channel)
        if ch_level is None:
            return True  # 跟随 sink 级别
        return msg_level >= ch_level

    return _filter


# ═══════════════════════════════════════════════════════════════════════════════
# 调用者追踪
# ═══════════════════════════════════════════════════════════════════════════════


def caller_info(depth: int = 1) -> str:
    """返回调用者的全量相对路径信息。

    格式: ``ui/decisive/preparation.py:276 in swap_fleet``

    Parameters
    ----------
    depth:
        栈深度。1 = 调用 ``caller_info()`` 的函数的调用者。

    Returns
    -------
    str
        ``相对路径:行号 in 函数名``，获取失败返回 ``<unknown>``。
    """
    try:
        frame = inspect.stack()[depth + 1]
        filepath = Path(frame.filename)
        try:
            rel = filepath.relative_to(_PROJECT_ROOT).as_posix()
        except ValueError:
            rel = filepath.name
        return f'{rel}:{frame.lineno} in {frame.function}'
    except Exception:
        return '<unknown>'


# ═══════════════════════════════════════════════════════════════════════════════
# 通道 logger 工厂
# ═══════════════════════════════════════════════════════════════════════════════


def get_logger(channel: str):
    """创建绑定了通道的 logger 实例。

    Parameters
    ----------
    channel:
        通道名称，如 ``"combat"``、``"vision.pixel"``。

    Returns
    -------
    loguru.Logger
        绑定了 ``ch=channel`` 的 logger，可直接调用 ``.info()`` 等。

    Examples
    --------
    ::

        _log = get_logger("combat")
        _log.info("战斗结束: {}", result)
    """
    return logger.bind(ch=channel)


# ═══════════════════════════════════════════════════════════════════════════════
# setup_logger
# ═══════════════════════════════════════════════════════════════════════════════


def setup_logger(
    log_dir: Path | None = None,
    level: str = 'INFO',
    rotation: str = '10 MB',
    retention: str = '7 days',
    save_images: bool = False,
    channels: dict[str, str] | None = None,
) -> None:
    """配置全局 loguru logger。

    日志策略：
    - 控制台：按 *level* 过滤，受 *channels* 通道设置调节。
    - 文件（全量）：始终以 DEBUG 级别记录，**不受** 通道过滤影响。
    - 文件（过滤）：与控制台 *level* 一致，受 *channels* 过滤。

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
    channels:
        通道级别覆盖。键为通道名（支持前缀匹配），值为级别字符串。

        示例::

            channels={
                "vision.pixel": "TRACE",   # 开启逐像素详情
                "vision.image": "TRACE",   # 开启逐模板详情
                "emulator": "INFO",        # 屏蔽 click/swipe 的 DEBUG
            }

        未列出的通道跟随 sink 自身的 *level* 设置。
    """
    global _image_dir, _channel_levels

    # 解析通道级别配置
    _channel_levels = {}
    if channels:
        for ch_name, ch_level_str in channels.items():
            ch_level_str = ch_level_str.upper()
            if ch_level_str not in _LEVEL_MAP:
                raise ValueError(f"无效的日志级别 '{ch_level_str}'，有效值: {list(_LEVEL_MAP)}")
            _channel_levels[ch_name] = _LEVEL_MAP[ch_level_str]

    # 移除所有已注册的 handler，避免重复输出
    logger.remove()

    # 注册 patcher：为每条记录附加可点击的相对路径 + ch 默认值
    logger.configure(patcher=_src_patcher)

    _FMT = (
        '<green>{time:HH:mm:ss.SSS}</green> | '
        '<level>{level:8}</level> | '
        '<cyan>{extra[src]}</cyan> | '
        '{message}'
    )

    # 控制台 sink — 级别过滤 + 通道过滤
    console_level_no = _LEVEL_MAP.get(level.upper(), 20)
    logger.add(
        sys.stderr,
        level=0,  # 由 filter 全权控制
        filter=_make_channel_filter(console_level_no),
        format=_FMT,
    )

    # 文件输出
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)

        # 全量文件：固定 DEBUG，**不做**通道过滤（记录一切）
        logger.add(
            log_dir / 'autowsgr_{time:YYYY-MM-DD}.debug.log',
            level='DEBUG',
            rotation=rotation,
            retention=retention,
            encoding='utf-8',
            format=_FMT,
        )

        # 过滤文件：与控制台 level 一致，受通道过滤
        if level.upper() != 'DEBUG':
            logger.add(
                log_dir / 'autowsgr_{time:YYYY-MM-DD}.log',
                level=0,
                filter=_make_channel_filter(console_level_no),
                rotation=rotation,
                retention=retention,
                encoding='utf-8',
                format=_FMT,
            )

        # 图片目录
        if save_images:
            _image_dir = log_dir / 'images'
            _image_dir.mkdir(parents=True, exist_ok=True)
            logger.debug('截图存储目录: {}', _image_dir)
    else:
        _image_dir = None

    # ── 静默第三方库的 Python logging 噪音 ──────────────────────────────
    for _noisy in (
        'airtest',
        'airtest.core.android.adb',
        'airtest.core.android.rotation',
        'airtest.utils.nbsp',
        'pocoui',
    ):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


def save_image(
    image: np.ndarray,
    tag: str = 'screenshot',
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

    target_dir = str(img_dir or _image_dir)
    target_dir = Path(target_dir)
    if target_dir is None:
        raise ValueError('未配置图片保存目录，请在 setup_logger 中设置 log_dir 并启用 save_images')

    target_dir.mkdir(parents=True, exist_ok=True)
    ts = _time.strftime('%H%M%S') + f'_{int(_time.monotonic() * 1000) % 1000:03d}'
    filename = f'{tag}_{ts}.png'
    path = target_dir / filename

    # cv2.imwrite 期望 BGR 排列，而我们统一使用 RGB，写入前需转换
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    # 使用 imencode + write_bytes 避免 OpenCV C 层 ANSI 路径导致中文乱码
    ok, buf = cv2.imencode('.png', bgr)
    if ok:
        path.write_bytes(buf.tobytes())
        logger.debug('截图已保存: {}', path)
    else:
        logger.warning('截图保存失败: {}', path)
        return None
    return path
