"""ops 端到端测试公共工具。

提供 :func:`launch_for_test` 供各 ops 测试脚本调用，替代手动的
``ConfigManager.load() → ADBController → GameContext → ensure_game_ready``
流程，与生产环境的 :func:`autowsgr.scheduler.launcher.launch` 行为对齐。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.context import GameContext


if TYPE_CHECKING:
    from pathlib import Path


def launch_for_test(
    serial: str | None,
    log_dir: Path,
    log_level: str = 'DEBUG',
    *,
    with_ocr: bool = False,
) -> GameContext:
    """为 ops 端到端测试准备就绪的 GameContext。

    加载配置 → 覆盖日志目录/级别 → 连接设备 →
    构建 GameContext → ensure_game_ready → 返回就绪上下文。

    与 :func:`autowsgr.scheduler.launcher.launch` 的区别：

    * 使用测试专用的 *log_dir* 覆盖配置中的日志目录。
    * 默认 ``with_ocr=False`` 跳过 OCR 初始化（适用于不需要 OCR 的简单 ops）。

    Parameters
    ----------
    serial:
        ADB 设备序列号；为 ``None`` 时沿用配置文件或自动检测。
    log_dir:
        测试专用日志目录（覆盖配置文件 ``log.dir``）。
    log_level:
        日志级别，默认 ``"DEBUG"``。
    with_ocr:
        是否初始化 OCR 引擎（决战等需要 OCR 的场景置 ``True``）。

    Returns
    -------
    GameContext
        ``ctx.ctrl`` 已连接、游戏已在主页面。
        若 ``with_ocr=True`` 则 ``ctx.ocr`` 也已初始化。
    """
    from autowsgr.infra.logger import setup_logger
    from autowsgr.scheduler.launcher import Launcher

    launcher = Launcher()
    cfg = launcher.load_config()

    # 以测试指定 log_dir 覆盖配置中的日志目录
    channels = cfg.log.effective_channels or None
    setup_logger(log_dir=log_dir, level=log_level, save_images=True, channels=channels)

    # 以命令行指定的 serial 覆盖配置
    if serial is not None:
        new_emu = cfg.emulator.model_copy(update={'serial': serial})
        launcher.set_config(cfg.model_copy(update={'emulator': new_emu}))

    launcher.connect()

    if with_ocr:
        ctx = launcher.build_context()
    else:
        ctx = GameContext(ctrl=launcher.ctrl, config=launcher.config)
        launcher.ensure_ready(ctx)

    return ctx
