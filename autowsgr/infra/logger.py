"""全局日志配置。

使用方式::

    # 应用启动时调用一次
    from autowsgr.infra.logger import setup_logger
    setup_logger(log_dir=Path("log"))

    # 各模块直接使用 loguru
    from loguru import logger
    logger.info("开始出征 章节={} 地图={}", chapter, map_id)
"""

from __future__ import annotations

import sys
from pathlib import Path


def setup_logger(
    log_dir: Path | None = None,
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
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
    """
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
