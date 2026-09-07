"""E2E 快速实机验证框架 — 基座 (E2ERunner)。

算法说明:
1. 目标: 把 "连接设备 → 启动游戏 → 执行操作 → 判定结果" 的重复劳动收敛成一个
   基座, 验证脚本 (case) 只写业务步骤本身, 实现 "加一个文件 = 多一个可跑的实机
   验证"。
2. 初始化: 走生产同款 Launcher 流程 (load_config → setup_logger → connect →
   ensure_ready), 保证验证环境与 GUI / examples 脚本运行时行为一致;
   --no-launch 可跳过游戏就绪 (纯只读验证), --with-ocr 决定是否初始化 OCR。
3. 步骤执行: rt.action(label, fn) 执行任意函数并计时; 正常时原样返回 fn 的返回
   值, 抛异常时记为失败、自动截图存证并返回 FAILED 哨兵, case 据此短路退出。
4. 断言: rt.check(label, fn) 把返回值当 bool 判定, 用于次数 / 状态核对。
5. 汇总: finalize(overall) 汇总所有步骤的通过 / 失败, 结合 case 整体返回值
   给出进程退出码 (0 = 全部通过), 供终端与 CI 直接判断。
"""

from __future__ import annotations

# 处理 Windows GBK 编码兼容性 (中文输出在默认代码页下可能乱码)
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: S110
    pass  # reconfigure 不可用时继续使用默认编码


# ═══════════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class StepRec:
    """单条步骤记录 (action / check 各记一条)。"""

    label: str  # 步骤描述 (中文, 显示给用户)
    ok: bool  # 是否通过 (action: 是否抛异常; check: 断言结果)
    duration_ms: int = 0  # 耗时 (毫秒)
    error: str | None = None  # 异常信息 (失败时)


@dataclass
class RunnerState:
    """E2ERunner 的步骤累计状态。"""

    steps: list[StepRec] = field(default_factory=list)

    @property
    def failed(self) -> int:
        """失败步骤数。"""
        return sum(1 for s in self.steps if not s.ok)


# ═══════════════════════════════════════════════════════════════════════════════
# 基座
# ═══════════════════════════════════════════════════════════════════════════════


class E2ERunner:
    """单个 E2E case 的执行基座。

    职责: 设备连接、游戏就绪、步骤计时与记录、失败截图、汇总与退出码。
    case 只需调用 :meth:`action` / :meth:`check` / :meth:`note` 组织自己的步骤。
    """

    # 失败哨兵: action 抛异常时返回它 (区别于业务返回值 None/False/空列表)
    FAILED = object()

    def __init__(
        self,
        case_name: str,
        case_args: Any,
        *,
        serial: str | None = None,
        debug: bool = False,
        no_launch: bool = False,
        with_ocr: bool = False,
        fast_ocr: bool = False,
    ) -> None:
        self.case_name = case_name
        self.args = case_args  # case 自己的参数 namespace (run.py 解析后传入)
        self.serial = serial  # ADB 序列号; None 时用 usersettings.yaml 配置
        self.debug = debug  # True 时日志级别 DEBUG
        self.no_launch = no_launch  # True 时跳过游戏就绪 (纯只读验证)
        self.with_ocr = with_ocr  # True 时初始化 OCR 引擎 (编队识别等需要)
        self.fast_ocr = fast_ocr  # True 时仅在本次 E2E 内切换 CPU FastOCR
        self.state = RunnerState()
        self.ctx: Any = None  # GameContext (prepare() 成功后可用)
        self._launcher: Any = None
        self._connected = False
        self._cleanup_done = False
        self._recovery_in_progress = False
        # 每次运行独立目录: logs/e2e_tools/<case>/<时间戳>
        stamp = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
        self.log_dir = Path('logs/e2e_tools') / case_name / stamp

    # ── 初始化 ─────────────────────────────────────────────────────

    def prepare(self) -> bool:
        """连接设备并准备游戏环境。

        流程与生产 launch() 对齐: 读配置 → 初始化日志 → 连接设备 → 游戏就绪。
        ``no_launch=True`` 时只连接不启动游戏 (截图/页面识别等只读验证)。
        """
        from autowsgr.infra.logger import setup_logger
        from autowsgr.scheduler.launcher import Launcher

        launcher = Launcher()
        # Keep the handle before connect so a partially connected controller is
        # still released when connection or context construction fails.
        self._launcher = launcher
        cfg = launcher.load_config()

        if self.fast_ocr:
            ocr_cfg = cfg.ocr.model_copy(update={'enhanced_ship_ocr': True})
            launcher.set_config(cfg.model_copy(update={'ocr': ocr_cfg}))

        # 日志目录/级别以本次运行为准, 通道配置沿用 usersettings.yaml
        channels = cfg.log.effective_channels or None
        setup_logger(
            log_dir=self.log_dir,
            level='DEBUG' if self.debug else 'INFO',
            save_images=True,
            channels=channels,
        )

        # 命令行指定 serial 时覆盖配置
        if self.serial is not None:
            emu = cfg.emulator.model_copy(update={'serial': self.serial})
            launcher.set_config(cfg.model_copy(update={'emulator': emu}))

        # 连接设备
        try:
            launcher.connect()
            self._connected = True
            serial = launcher.config.emulator.serial or 'auto'
            res = launcher.ctrl.resolution
            print(f'  [OK] 设备已连接: {serial} {res[0]}x{res[1]}')
        except Exception as exc:
            self._record('连接设备', ok=False, error=str(exc))
            print(f'  [FAIL] 设备连接失败: {exc}')
            return False

        try:
            # 组装 GameContext (与 testing/ops 的 launch_for_test 同款流程)
            from autowsgr.context import GameContext

            if self.with_ocr:
                self.ctx = launcher.build_context()  # 含 OCR 引擎
            else:
                self.ctx = GameContext(ctrl=launcher.ctrl, config=launcher.config, ocr=None)

            if self.no_launch:
                # 显式只读模式: 不启动/导航游戏, 供截图和页面识别诊断使用。
                return True

            # 所有正常 E2E 都从同一个业务初始化入口开始，避免 OCR 分支
            # 与普通分支产生不同的首页/浮层状态。
            self._initialize_game()
        except Exception as exc:
            self._record('初始化游戏', ok=False, error=str(exc))
            print(f'  [FAIL] 游戏初始化失败: {exc}')
            self._error_screenshot('prepare')
            return False
        return True

    # ── 步骤 API (case 调用) ───────────────────────────────────────

    def action(self, label: str, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        """执行一个操作步骤。

        正常返回 fn 的返回值; 抛异常时记录失败、自动截图、返回 ``rt.FAILED``。
        case 约定写法::

            results = rt.action('跑常规战', run_normal_fight_from_yaml, ctx, '1-1')
            if results is rt.FAILED:
                return False
        """
        t0 = time.monotonic()
        try:
            if not self._ensure_game_running():
                raise RuntimeError('游戏进程已退出且重新初始化失败')
            value = fn(*args, **kwargs)
            # 操作期间进程可能被外部关闭。此处只恢复运行环境，不重放
            # 已经执行过的业务函数，避免点击类操作被重复提交。
            if not self._ensure_game_running():
                raise RuntimeError('操作后游戏进程已退出且重新初始化失败')
        except Exception as exc:
            self._recover_after_error()
            self._record(label, ok=False, error=str(exc), t0=t0)
            print(f'  [FAIL] {label}: {exc}')
            self._error_screenshot(label)
            return self.FAILED
        self._record(label, ok=True, t0=t0)
        print(f'  [OK] {label} ({self._ms_since(t0)}ms)')
        return value

    def check(self, label: str, fn: Any, /, *args: Any, **kwargs: Any) -> bool:
        """断言步骤: 把 fn 返回值当 bool 判定, 打印 PASS/FAIL。"""
        t0 = time.monotonic()
        try:
            if not self._ensure_game_running():
                raise RuntimeError('游戏进程已退出且重新初始化失败')
            passed = bool(fn(*args, **kwargs))
            error: str | None = None
            if not self._ensure_game_running():
                passed = False
                error = '检查后游戏进程已退出且重新初始化失败'
        except Exception as exc:
            self._recover_after_error()
            passed = False
            error = str(exc)
        self._record(label, ok=passed, error=error, t0=t0)
        mark = 'PASS' if passed else 'FAIL'
        suffix = f': {error}' if error else ''
        print(f'  [{mark}] {label}{suffix}')
        return passed

    def note(self, msg: str) -> None:
        """打印一条说明信息 (不计入步骤, 不影响判定)。"""
        print(f'  [i] {msg}')

    # ── 兜底与汇总 ─────────────────────────────────────────────────

    def unexpected(self, exc: Exception) -> None:
        """case 主体自身抛出的未捕获异常兜底 (记为一条失败步骤)。"""
        self._record(f'case 异常 ({type(exc).__name__})', ok=False, error=str(exc))
        print(f'  [FAIL] case 异常: {exc}')
        self._error_screenshot('case_crash')

    def finalize(self, *, overall: bool = True) -> int:
        """先收口游戏生命周期，再打印汇总并返回进程退出码。"""
        self.cleanup()
        total = len(self.state.steps)
        failed = self.state.failed
        print()
        print('═' * 68)
        for i, s in enumerate(self.state.steps, 1):
            mark = 'OK  ' if s.ok else 'FAIL'
            dur = f'{s.duration_ms}ms' if s.duration_ms else ''
            err = f'  ← {s.error}' if s.error else ''
            print(f'  [{mark}] [{i:02d}] {s.label}  {dur}{err}')
        verdict = 'PASS' if (failed == 0 and overall) else 'FAIL'
        print()
        print(f'  {self.case_name}: {total} 步, 失败 {failed} 步 → {verdict}')
        print(f'  日志目录: {self.log_dir.resolve()}')
        print('═' * 68)
        return 0 if verdict == 'PASS' else 1

    def cleanup(self) -> None:
        """无论 case 结果如何，尝试回主页并释放设备连接。"""
        if self._cleanup_done:
            return
        self._cleanup_done = True

        if self.ctx is not None and not self.no_launch:
            t0 = time.monotonic()
            try:
                self._initialize_game()
            except Exception as exc:
                self._record('清理: 回到主页面', ok=False, error=str(exc), t0=t0)
                print(f'  [FAIL] 清理: 回到主页面: {exc}')
                self._error_screenshot('cleanup')
            else:
                self._record('清理: 回到主页面', ok=True, t0=t0)
                print(f'  [OK] 清理: 回到主页面 ({self._ms_since(t0)}ms)')

        if self._launcher is None or not self._connected:
            return
        try:
            self._launcher.ctrl.disconnect()
            self._connected = False
        except Exception as exc:
            self._record('清理: 断开设备', ok=False, error=str(exc))
            print(f'  [FAIL] 清理: 断开设备: {exc}')

    # ── 游戏生命周期 ─────────────────────────────────────────────

    def _game_package(self) -> str:
        """返回当前配置对应的 Android 包名。"""
        if self.ctx is None:
            raise RuntimeError('GameContext 尚未构造')
        return self.ctx.config.account.package_name

    def _initialize_game(self) -> None:
        """调用当前启动器的就绪入口，保证终态为首页待机。"""
        if self.ctx is None:
            raise RuntimeError('GameContext 尚未构造')
        if self._launcher is None:
            raise RuntimeError('Launcher 尚未构造')
        self._launcher.ensure_ready(self.ctx)

    def _ensure_game_running(self) -> bool:
        """检测游戏是否仍在运行；异常退出时只重新初始化一次。"""
        if self.no_launch or self.ctx is None:
            return True
        try:
            running = self.ctx.ctrl.is_app_running(self._game_package())
        except Exception as exc:
            self.note(f'无法检查游戏进程: {exc}')
            return False
        if running or self._recovery_in_progress:
            return running

        self._recovery_in_progress = True
        try:
            self.note('检测到游戏进程异常退出，重新初始化')
            self._initialize_game()
        except Exception as exc:
            self.note(f'重新初始化失败: {exc}')
            return False
        else:
            return True
        finally:
            self._recovery_in_progress = False

    def _recover_after_error(self) -> None:
        """在步骤异常后尝试恢复已退出的游戏进程。"""
        if self.no_launch or self.ctx is None or self._recovery_in_progress:
            return
        try:
            self._ensure_game_running()
        except Exception as recovery_error:
            self.note(f'异常后恢复失败: {recovery_error}')

    # ── 内部工具 ───────────────────────────────────────────────────

    @staticmethod
    def _ms_since(t0: float) -> int:
        return int((time.monotonic() - t0) * 1000)

    def _record(
        self,
        label: str,
        *,
        ok: bool,
        error: str | None = None,
        t0: float | None = None,
    ) -> None:
        self.state.steps.append(
            StepRec(
                label=label,
                ok=ok,
                duration_ms=self._ms_since(t0) if t0 is not None else 0,
                error=error,
            )
        )

    def _error_screenshot(self, label: str) -> None:
        """失败时自动截图存证 (截图本身失败则静默跳过)。"""
        if self.ctx is None or self.ctx.ctrl is None:
            return
        try:
            from autowsgr.infra import save_image

            screen = self.ctx.ctrl.screenshot()
            tag = f'e2e_fail_{label.replace(" ", "_")[:40]}'
            path = save_image(screen, tag=tag)
            if path:
                print(f'        失败截图: {path}')
        except Exception:  # noqa: S110
            pass
