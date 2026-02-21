"""游戏重启交互式端到端测试。

直接运行此脚本即可自动连接设备并测试游戏重启流程，适合快速手动验证重启功能。

用法::

    # 自动检测设备
    python testing/ops/startup.py

    # 指定设备 serial
    python testing/ops/startup.py 127.0.0.1:16384

可选参数::

    --log-dir     日志目录 (默认 logs/interactive/restart_game)
    --package     游戏包名 (默认: 官服)

注意: 运行此脚本将会强制关闭并重启游戏，该过程大约需要 30-60 秒。
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

# ── UTF-8 输出兼容 (Windows 终端) ──
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
    except Exception:
        pass

from loguru import logger

from autowsgr.emulator import ADBController
from autowsgr.infra import setup_logger
from autowsgr.ops.startup import restart_game
from autowsgr.types import GameAPP, PageName
from autowsgr.vision import PixelChecker


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="游戏重启交互式端到端测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "serial",
        nargs="?",
        default=None,
        metavar="SERIAL",
        help="ADB serial (留空则自动检测唯一设备)",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        metavar="DIR",
        help="日志输出目录 (默认: logs/interactive/restart_game)",
    )
    parser.add_argument(
        "--package",
        default=None,
        metavar="PKG",
        help="游戏包名 (默认: 官服)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # ── 日志 ──
    log_dir = Path(args.log_dir) if args.log_dir else Path("logs/interactive/restart_game")
    setup_logger(log_dir=log_dir, level="DEBUG", save_images=True)

    serial: str | None = args.serial or None

    # 确定包名
    if args.package:
        package = args.package
        logger.info("使用指定包名: {}", package)
    else:
        package = GameAPP.official.package_name
        logger.info("使用官服包名: {}", package)

    logger.info("=" * 50)
    logger.info("游戏重启交互式测试")
    logger.info("  日志: {}", log_dir)
    logger.info("=" * 50)

    # ── 连接设备 ──
    logger.info("正在连接设备{}...", f" ({serial})" if serial else " (自动检测)")
    ctrl = ADBController(serial=serial)
    try:
        dev_info = ctrl.connect()
        logger.info(
            "已连接: {}  分辨率: {}x{}",
            dev_info.serial,
            dev_info.resolution[0],
            dev_info.resolution[1],
        )
    except Exception as exc:
        logger.error("连接设备失败: {}", exc)
        sys.exit(1)

    # ── 执行重启 ──
    try:
        logger.info("开始重启游戏...")
        restart_game(ctrl, package=package)
        logger.info("重启调用完成，等待游戏启动...")

        # 等待游戏启动（约 30-60 秒）
        max_wait = 90
        start_time = time.time()
        screenshoot_ok = False

        while time.time() - start_time < max_wait:
            try:
                screen = ctrl.screenshot()
                if screen is not None and screen.size > 0:
                    screenshoot_ok = True
                    logger.info("游戏已启动，获得有效截图")
                    break
                logger.debug("等待游戏启动...")
            except Exception as e:
                logger.debug("获取截图失败 (预期): {}", e)
            time.sleep(2)

        if not screenshoot_ok:
            logger.warning("等待超时，游戏可能未成功启动")
            sys.exit(1)

        # ── 验证结果 ──
        logger.info("=" * 50)
        logger.info("✓ 游戏重启测试通过")
        logger.info("  - 成功强制停止并冷启动游戏")
        logger.info("  - 游戏已启动且能够获取截图")
        logger.info("=" * 50)

    except Exception as exc:
        logger.error("重启游戏失败: {}", exc)
        logger.error("错误堆栈:", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
