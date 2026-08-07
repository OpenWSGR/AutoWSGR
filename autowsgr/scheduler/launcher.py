"""启动器 — 构造就绪的 AndroidController + GameContext。

从零开始完成从配置加载到游戏就绪的全部流程::

    配置加载 → 日志初始化 → 设备连接 → 游戏启动 → 构造 GameContext

使用方式::

    from autowsgr.scheduler.launcher import launch

    ctx = launch("user_settings.yaml")
    # ctx.ctrl  → 已连接的 ScrcpyController
    # ctx.config → UserConfig
    # ctx.ocr   → OCREngine (已初始化)
    # 游戏已在主页面

如需更精细控制，可直接使用 :class:`Launcher`::

    launcher = Launcher(config_path="user_settings.yaml")
    launcher.load_config()
    launcher.connect()
    ctx = launcher.build_context()
    launcher.ensure_ready(ctx)
"""

from __future__ import annotations

import os
from pathlib import Path

from autowsgr.context import GameContext
from autowsgr.emulator import AndroidController, ScrcpyController
from autowsgr.infra import ConfigManager, UserConfig
from autowsgr.infra.logger import get_logger, setup_logger
from autowsgr.vision import EasyOCREngine, OCREngine


_log = get_logger('scheduler')


class Launcher:
    """可定制的启动器。

    分步骤构造 ``AndroidController`` + ``GameContext``，
    每一步可独立调用，便于单元测试或自定义流程。

    配置查找顺序:

    1. 显式传入 ``config_path`` → 直接加载。
    2. ``config_path=None`` → 自动检测当前目录下 ``usersettings.yaml``。
    3. 上述文件不存在 → 使用内置默认值。

    也可跳过文件加载，通过 :meth:`set_config` 直接注入
    :class:`UserConfig` 实例。

    Parameters
    ----------
    config_path:
        用户配置文件路径 (YAML)。为 ``None`` 时自动检测。
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = Path(config_path) if config_path else None
        self._config: UserConfig | None = None
        self._ctrl: AndroidController | None = None
        self._ocr: OCREngine | None = None

    # ── 配置 ──

    def load_config(self) -> UserConfig:
        """从 YAML 加载配置并初始化日志。

        配置文件不存在时使用内置默认配置。

        如果构造时未传入 ``config_path``，将由 :class:`ConfigManager`
        自动检测当前目录下的 ``usersettings.yaml``；若也不存在则
        使用内置默认配置。
        """
        if self._config_path is not None:
            _log.info('[Launcher] 加载配置: {}', self._config_path)
        else:
            _log.info('[Launcher] 未指定配置文件，尝试自动检测')
        self._config = ConfigManager.load(self._config_path)
        log_cfg = self._config.log
        setup_logger(
            log_cfg.dir,
            log_cfg.level,
            save_images=os.getenv('AUTOWSGR_SAVE_IMAGES', '').lower() == 'true',
            channels=log_cfg.effective_channels or None,
        )
        ch_summary = log_cfg.effective_channels
        _log.info(
            '[Launcher] 日志初始化完成: level={}, 通道覆盖={}',
            log_cfg.level,
            ch_summary or '无',
        )
        return self._config

    def set_config(self, config: UserConfig) -> None:
        """手动设置配置（替代 :meth:`load_config`）。"""
        self._config = config

    @property
    def config(self) -> UserConfig:
        if self._config is None:
            raise RuntimeError('配置未加载，请先调用 load_config() 或 set_config()')
        return self._config

    # ── 设备连接 ──

    def connect(self) -> AndroidController:
        """创建并连接设备控制器。

        默认使用 ScrcpyController（基于 scrcpy 协议截图）。

        Returns
        -------
        AndroidController
            已建立连接的设备控制器。
        """
        cfg = self.config
        _log.info('[Launcher] 连接设备 (serial={})', cfg.emulator.serial or 'auto')
        self._ctrl = ScrcpyController(
            serial=cfg.emulator.serial,
            config=cfg.emulator,
        )
        self._ctrl.connect()
        return self._ctrl

    @property
    def ctrl(self) -> AndroidController:
        if self._ctrl is None:
            raise RuntimeError('设备未连接，请先调用 connect()')
        return self._ctrl

    # ── OCR ──

    def create_ocr(self) -> OCREngine:
        """根据配置创建通用 OCR 引擎 (EasyOCR)。"""
        cfg = self.config
        _log.info('[Launcher] 创建通用 OCR 引擎: EasyOCR')
        gpu = cfg.ocr.gpu
        gpu_override = os.getenv('AUTOWSGR_OCR_GPU_MODE', '').lower()
        if gpu_override == 'cuda':
            gpu = True
        elif gpu_override == 'cpu':
            gpu = False
        self._ocr = EasyOCREngine.create(gpu=gpu, mirror=cfg.ocr.mirror)
        # 同步船池感知匹配置信度到 ocr 模块
        from autowsgr.vision.ocr import set_ship_name_match_confidence
        from autowsgr.vision.ocr_rules import (
            set_user_ship_name_aliases,
            set_user_ship_name_corrections,
        )

        set_ship_name_match_confidence(cfg.ocr.ship_name_match_confidence)
        loaded_rules = set_user_ship_name_corrections(cfg.ocr.ship_name_corrections)
        loaded_aliases = set_user_ship_name_aliases(cfg.ocr.ship_name_aliases)
        if cfg.ocr.ship_name_match_confidence > 0.0:
            _log.info(
                '[Launcher] OCR置信度匹配机制加载（当前参数：{:.2f}）',
                cfg.ocr.ship_name_match_confidence,
            )
        if loaded_rules:
            _log.info('[Launcher] OCR用户舰名规则加载（有效规则：{}）', loaded_rules)
        if loaded_aliases:
            _log.info('[Launcher] OCR用户舰名别名加载（有效别名：{}）', loaded_aliases)
        return self._ocr

    def create_ship_ocr(self) -> OCREngine | None:
        """根据配置创建增强船只识别 OCR 引擎 (FastOCR / PP-OCRv6-small)。

        仅在 ``cfg.ocr.enhanced_ship_ocr`` 开启时创建；
        默认关闭，返回 ``None``，船只识别节点继续使用默认 EasyOCR。
        """
        cfg = self.config
        if not cfg.ocr.enhanced_ship_ocr:
            _log.info('[Launcher] 增强船只识别 OCR 未开启，船只识别节点继续使用 EasyOCR')
            return None
        _log.info('[Launcher] 创建增强船只识别 OCR 引擎: FastOCR (PP-OCRv6-small)')
        return OCREngine.create(engine='fastocr', gpu=False)

    # ── 构造 GameContext ──

    def build_context(self) -> GameContext:
        """构造 GameContext（基础设施 + 默认游戏状态）。

        必须在 :meth:`connect` 之后调用。
        若未手动调用 :meth:`create_ocr`，会自动初始化 OCR。

        Returns
        -------
        GameContext
            已注入 ``ctrl``、``config``、``ocr`` 的上下文。
        """
        if self._ocr is None:
            self.create_ocr()

        ctx = GameContext(
            ctrl=self.ctrl,
            config=self.config,
            ocr=self._ocr,
            ship_ocr=self.create_ship_ocr(),
        )
        ship_engine = (
            'FastOCR (PP-OCRv6-small)' if ctx.ship_ocr is not None else '未启用 (沿用 EasyOCR)'
        )
        _log.info('[Launcher] OCR 加载完成: 通用引擎=EasyOCR, 船只识别引擎={}', ship_engine)
        _log.info('[Launcher] GameContext 已构建')
        return ctx

    # ── 游戏启动 ──

    def ensure_ready(self, ctx: GameContext) -> None:
        """确保游戏已启动并位于主页面。

        Parameters
        ----------
        ctx:
            已构建的 GameContext（内部使用 ``ctx.ctrl``）。
        """
        from autowsgr.ops.startup import ensure_game_ready

        app = ctx.config.account.game_app
        _log.info('[Launcher] 确保游戏就绪 (app={})', app.value)
        ensure_game_ready(ctx, app)

    # ── 一步到位 ──

    def launch(self, ensure_game: bool = True) -> GameContext:
        """一步完成: 加载配置 → 连接 → 构造上下文 → 启动游戏。

        Returns
        -------
        GameContext
            完全就绪的游戏上下文。
        """
        self.load_config()
        self.connect()
        ctx = self.build_context()
        if ensure_game:
            self.ensure_ready(ctx)
        _log.info('[Launcher] 启动完成，游戏已就绪')
        return ctx


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════════════


def launch(config_path: str | Path | None = None, ensure_game: bool = True) -> GameContext:
    """一站式启动入口。

    加载配置 → 连接模拟器 → 启动游戏 → 返回就绪的 :class:`GameContext`。

    Parameters
    ----------
    config_path:
        用户配置文件路径 (YAML)。为 ``None`` 时自动检测当前目录下
        的 ``usersettings.yaml``，若也不存在则使用内置默认配置。

    Returns
    -------
    GameContext
        ``ctx.ctrl`` 已连接、游戏已在主页面。

    Examples
    --------
    ::

        from autowsgr.scheduler import launch

        # 显式指定配置路径
        ctx = launch("my_settings.yaml")

        # 自动检测 usersettings.yaml 或使用默认值
        ctx = launch()
    """
    return Launcher(config_path).launch(ensure_game=ensure_game)
