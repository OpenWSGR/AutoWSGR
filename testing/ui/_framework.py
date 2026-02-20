"""UI 控制器端到端测试框架。

提取自 smoke_ui_walk.py，适用于单个 UI 控制器的端到端测试。

每个控制器的 e2e.py 均可:
- 作为独立脚本直接运行: ``python testing/ui/<page>/e2e.py [serial] [--auto] [--debug]``
- 在 CI 跳过 (需要真实设备，不参与常规 pytest)

典型使用::

    from testing.ui._framework import UIControllerTestRunner, parse_e2e_args

    def run_test(runner: UIControllerTestRunner) -> None:
        from autowsgr.ui.xxx_page import XxxPage
        page = XxxPage(runner.ctrl)

        runner.verify_current("初始验证: Xxx页面", "Xxx页面", XxxPage.is_current_page)
        runner.execute_step(
            "内部操作",
            "Xxx页面",
            XxxPage.is_current_page,
            lambda: page.do_something(),
        )

    if __name__ == "__main__":
        args = parse_e2e_args("Xxx页面 e2e 测试", precondition="在 Xxx 页面")
        ...
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

# 处理 Windows GBK 编码兼容性
import io
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass  # 如果配置失败，继续使用默认编码

if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.emulator import ADBController


# ═══════════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════════


class StepResult(str, Enum):
    """单步执行结果。"""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class StepRecord:
    """单步记录。"""

    index: int                       # 步骤序号 (1-based)
    action: str                      # 动作描述 (中文)
    expected_page: str               # 期望页面名
    actual_page: str | None = None   # 实际识别到的页面名
    page_check: bool = False         # is_current_page 结果
    result: StepResult = StepResult.SKIP
    screenshot_path: str | None = None
    error_msg: str | None = None
    duration_ms: int = 0             # 动作耗时 (毫秒)


@dataclass
class ControllerTestReport:
    """单控制器测试报告。"""

    controller: str = ""             # 控制器名称
    start_time: str = ""
    end_time: str = ""
    mode: str = "interactive"
    total_steps: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    steps: list[StepRecord] = field(default_factory=list)

    def add(self, rec: StepRecord) -> None:
        self.steps.append(rec)
        self.total_steps += 1
        match rec.result:
            case StepResult.PASS:
                self.passed += 1
            case StepResult.FAIL:
                self.failed += 1
            case StepResult.SKIP:
                self.skipped += 1
            case StepResult.ERROR:
                self.errors += 1


# ═══════════════════════════════════════════════════════════════════════════════
# 终端 I/O
# ═══════════════════════════════════════════════════════════════════════════════


def _print_header(title: str) -> None:
    print()
    print("═" * 68)
    print(f"  {title}")
    print("═" * 68)


def _print_step(index: int, action: str) -> None:
    print()
    print("─" * 68)
    print(f"  [{index:03d}] {action}")
    print("─" * 68)


class _Sym:
    OK = "[OK]"
    FAIL = "[FAIL]"
    INFO = "[i]"
    WARN = "[!]"


def ok(msg: str) -> None:
    print(f"  {_Sym.OK} {msg}")


def fail(msg: str) -> None:
    print(f"  {_Sym.FAIL} {msg}")


def info(msg: str) -> None:
    print(f"  {_Sym.INFO} {msg}")


def warn(msg: str) -> None:
    print(f"  {_Sym.WARN} {msg}")


def _prompt_step(index: int, action: str, auto_mode: bool) -> str:
    """显示步骤提示并获取用户指令。

    Returns ``"run"`` / ``"skip"`` / ``"quit"``
    """
    _print_step(index, action)
    if auto_mode:
        return "run"
    ans = input("  [Enter] 执行  |  [s] 跳过  |  [q] 退出: ").strip().lower()
    if ans == "q":
        return "quit"
    return "skip" if ans == "s" else "run"


def _safe_tag(raw: str) -> str:
    """将动作描述转成文件名安全的字符串。"""
    return (
        raw.replace(" ", "_")
        .replace("→", "to")
        .replace("◁", "back")
        .replace(":", "")
        .replace("：", "")
        .replace("*", "")
        .replace("?", "")
        .replace('"', "")
        .replace("<", "")
        .replace(">", "")
        .replace("|", "")
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 核心: 步骤执行器
# ═══════════════════════════════════════════════════════════════════════════════


class UIControllerTestRunner:
    """UI 控制器端到端测试执行器。

    Parameters
    ----------
    ctrl:
        已连接的 ADBController 实例。
    controller_name:
        被测控制器名称 (用于报告)。
    log_dir:
        截图和报告输出目录。
    auto_mode:
        ``True`` 时全自动执行，不等待用户确认。
    pause:
        每步动作执行后的等待时间 (秒)，供 UI 动画完成。
    """

    def __init__(
        self,
        ctrl: "ADBController",
        controller_name: str = "",
        log_dir: Path | None = None,
        *,
        auto_mode: bool = False,
        pause: float = 1.5,
    ) -> None:
        from autowsgr.infra import save_image as _save_image  # lazy import

        self.ctrl = ctrl
        self.auto_mode = auto_mode
        self.pause = pause
        self._log_dir = log_dir or Path("logs/e2e") / controller_name
        self._save_image = _save_image
        self.report = ControllerTestReport(
            controller=controller_name,
            mode="auto" if auto_mode else "interactive",
            start_time=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._step_counter = 0
        self._aborted = False

    # ── 截图 ─────────────────────────────────────────────────────────

    def _take_screenshot(self, tag: str) -> tuple[np.ndarray, Path | None]:
        screen = self.ctrl.screenshot()
        path = self._save_image(screen, tag=tag)
        return screen, path

    # ── 单步执行 ─────────────────────────────────────────────────────

    def execute_step(
        self,
        action: str,
        expected_page: str,
        checker: "Callable[[np.ndarray], bool]",
        do_action: "Callable[[], None]",
        *,
        screenshot_tag: str = "",
    ) -> StepRecord | None:
        """执行单个测试步骤。

        Parameters
        ----------
        action:
            步骤描述（显示给用户）。
        expected_page:
            动作执行后期望到达的页面名称。
        checker:
            目标页面的 ``is_current_page`` 函数。
        do_action:
            执行导航操作的 callable（无参）。
        screenshot_tag:
            截图文件名 tag，为空则自动生成。

        Returns
        -------
        StepRecord | None
            步骤记录。若用户中止返回 None。
        """
        if self._aborted:
            return None

        self._step_counter += 1
        idx = self._step_counter

        user_choice = _prompt_step(idx, action, self.auto_mode)
        if user_choice == "quit":
            self._aborted = True
            return None
        if user_choice == "skip":
            rec = StepRecord(
                index=idx, action=action, expected_page=expected_page, result=StepResult.SKIP,
            )
            self.report.add(rec)
            info("已跳过")
            return rec

        raw_tag = screenshot_tag or f"{idx:03d}_{action}"
        tag = _safe_tag(raw_tag)
        rec = StepRecord(index=idx, action=action, expected_page=expected_page)
        t0 = time.monotonic()

        try:
            do_action()
            time.sleep(self.pause)

            screen, path = self._take_screenshot(tag)
            rec.screenshot_path = str(path) if path else None
            rec.duration_ms = int((time.monotonic() - t0) * 1000)

            from autowsgr.ui.page import get_current_page

            rec.page_check = checker(screen)
            rec.actual_page = get_current_page(screen)

            if rec.page_check:
                rec.result = StepResult.PASS
                ok(f"页面验证通过: {expected_page}")
                if rec.actual_page and rec.actual_page != expected_page:
                    warn(f"get_current_page='{rec.actual_page}' (期望='{expected_page}')")
            else:
                rec.result = StepResult.FAIL
                fail(f"页面验证失败: 期望'{expected_page}', 实际'{rec.actual_page or '未知'}'")

        except Exception as exc:
            rec.result = StepResult.ERROR
            rec.error_msg = str(exc)
            rec.duration_ms = int((time.monotonic() - t0) * 1000)
            fail(f"执行异常: {exc}")
            try:
                _, path = self._take_screenshot(f"{tag}_error")
                rec.screenshot_path = str(path) if path else None
            except Exception:
                pass

        self.report.add(rec)
        return rec

    def verify_current(
        self,
        action: str,
        expected_page: str,
        checker: "Callable[[np.ndarray], bool]",
    ) -> StepRecord | None:
        """只截图验证当前页面，不执行任何动作。"""
        return self.execute_step(
            action=action,
            expected_page=expected_page,
            checker=checker,
            do_action=lambda: None,
            screenshot_tag=f"{self._step_counter + 1:03d}_verify_{_safe_tag(expected_page)}",
        )

    def read_state(
        self,
        label: str,
        *,
        readers: "dict[str, Callable[[np.ndarray], object]] | None" = None,
    ) -> dict[str, object]:
        """截图并报告页面状态（不计入步骤记录）。

        Parameters
        ----------
        label:
            显示标签。
        readers:
            ``{字段名: lambda screen: 值}`` 字典，返回读取到的状态。
        """
        screen = self.ctrl.screenshot()
        result: dict[str, object] = {}
        if readers:
            for key, fn in readers.items():
                try:
                    val = fn(screen)
                    result[key] = val
                    info(f"{label} {key}: {val}")
                except Exception as exc:
                    warn(f"{label} {key}: 读取失败 ({exc})")
        return result

    # ── 属性 ─────────────────────────────────────────────────────────

    @property
    def aborted(self) -> bool:
        return self._aborted

    # ── 报告 ─────────────────────────────────────────────────────────

    def finalize(self) -> ControllerTestReport:
        """完成报告并保存 JSON。"""
        self.report.end_time = datetime.now(tz=timezone.utc).isoformat()

        report_dir = self._log_dir
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"e2e_report_{self.report.controller}.json"

        data = {
            "controller": self.report.controller,
            "start_time": self.report.start_time,
            "end_time": self.report.end_time,
            "mode": self.report.mode,
            "total_steps": self.report.total_steps,
            "passed": self.report.passed,
            "failed": self.report.failed,
            "skipped": self.report.skipped,
            "errors": self.report.errors,
            "steps": [
                {
                    "index": s.index,
                    "action": s.action,
                    "expected_page": s.expected_page,
                    "actual_page": s.actual_page,
                    "page_check": s.page_check,
                    "result": s.result.value,
                    "screenshot_path": s.screenshot_path,
                    "error_msg": s.error_msg,
                    "duration_ms": s.duration_ms,
                }
                for s in self.report.steps
            ],
        }
        report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        info(f"报告已保存: {report_path.resolve()}")
        return self.report

    def print_summary(self) -> None:
        """打印测试结果汇总。"""
        r = self.report
        _print_header(f"{r.controller} — e2e 测试结果汇总")
        print()
        _icon = {
            StepResult.PASS: _Sym.OK,
            StepResult.FAIL: _Sym.FAIL,
            StepResult.SKIP: "○",
            StepResult.ERROR: _Sym.WARN,
        }
        for s in r.steps:
            icon = _icon[s.result]
            dur = f"{s.duration_ms}ms" if s.duration_ms else ""
            pg = f"  [{s.actual_page or '?'}]" if s.result != StepResult.SKIP else ""
            print(
                f"  {icon} [{s.index:03d}] {s.action:<44s} "
                f"{s.result.value:5s} {dur:>8s}{pg}"
            )
        print()
        print(f"  总计: {r.total_steps} 步  通过: {r.passed}  "
              f"失败: {r.failed}  跳过: {r.skipped}  异常: {r.errors}")
        print()
        if r.failed == 0 and r.errors == 0:
            ok("全部通过!")
        else:
            fail(f"存在 {r.failed} 个失败 + {r.errors} 个异常")
        print("═" * 68)


# ═══════════════════════════════════════════════════════════════════════════════
# 页面导航保障
# ═══════════════════════════════════════════════════════════════════════════════


def reset_to_main_page(ctrl: "ADBController", pause: float = 1.5) -> bool:
    """从任意已知页面导航回主页面。

    按"叶页面 → 中间页面 → 主页面"顺序尝试每一级的返回操作，最多循环 5 次。

    Returns
    -------
    bool
        成功回到主页面时返回 ``True``，超出重试次数仍未到达则返回 ``False``。
    """
    from autowsgr.ui.backyard_page import BackyardPage
    from autowsgr.ui.bath_page import BathPage
    from autowsgr.ui.battle.preparation import BattlePreparationPage
    from autowsgr.ui.build_page import BuildPage
    from autowsgr.ui.canteen_page import CanteenPage
    from autowsgr.ui.decisive_battle_page import DecisiveBattlePage
    from autowsgr.ui.friend_page import FriendPage
    from autowsgr.ui.intensify_page import IntensifyPage
    from autowsgr.ui.main_page import MainPage
    from autowsgr.ui.map.page import MapPage
    from autowsgr.ui.mission_page import MissionPage
    from autowsgr.ui.sidebar_page import SidebarPage

    for _ in range(5):
        screen = ctrl.screenshot()
        if MainPage.is_current_page(screen):
            return True
        # 叶页面（深层）先返回
        if BathPage.is_current_page(screen):
            BathPage(ctrl).go_back()
        elif CanteenPage.is_current_page(screen):
            CanteenPage(ctrl).go_back()
        elif BuildPage.is_current_page(screen):
            BuildPage(ctrl).go_back()
        elif IntensifyPage.is_current_page(screen):
            IntensifyPage(ctrl).go_back()
        elif FriendPage.is_current_page(screen):
            FriendPage(ctrl).go_back()
        elif MissionPage.is_current_page(screen):
            MissionPage(ctrl).go_back()
        elif BattlePreparationPage.is_current_page(screen):
            BattlePreparationPage(ctrl).go_back()
        elif DecisiveBattlePage.is_current_page(screen):
            DecisiveBattlePage(ctrl).go_back()
        # 中间页面
        elif BackyardPage.is_current_page(screen):
            BackyardPage(ctrl).go_back()
        elif SidebarPage.is_current_page(screen):
            SidebarPage(ctrl).close()
        elif MapPage.is_current_page(screen):
            MapPage(ctrl).go_back()
        else:
            # 未知页面，无法自动返回
            return False
        time.sleep(pause)

    return False  # 5 次后仍未回到主页面


def ensure_page(
    ctrl: "ADBController",
    checker: "Callable[[np.ndarray], bool]",
    navigate_fn: "Callable[[], None] | None",
    page_name: str,
    *,
    auto_mode: bool,
    pause: float = 1.5,
) -> bool:
    """确保游戏当前处于目标页面，不在则尝试自动导航。

    流程
    ----
    1. 截图检测是否已在目标页面 → 直接返回 ``True``
    2. 若不在，调用 ``navigate_fn`` 尝试自动导航
    3. 再次检测 → 成功返回 ``True``
    4. 仍失败:

       - **交互模式**: 提示用户手动切换，等待确认后循环检测
       - **自动模式**: 打印错误消息，返回 ``False``
    """
    screen = ctrl.screenshot()
    if checker(screen):
        ok(f"已在目标页面: {page_name}")
        return True

    if navigate_fn is not None:
        info(f"尝试自动导航到: {page_name} ...")
        try:
            navigate_fn()
            time.sleep(pause)
            screen = ctrl.screenshot()
            if checker(screen):
                ok(f"自动导航成功: {page_name}")
                return True
        except Exception as exc:
            warn(f"自动导航遇到异常: {exc}")

    if auto_mode:
        fail(f"无法自动到达目标页面: {page_name}，终止测试")
        return False

    # 交互模式：提示用户手动切换
    warn(f"未能自动切换到: {page_name}")
    print(f"  请手动将游戏切换到 [{page_name}]")
    while True:
        ans = input("  [Enter] 已到达  |  [q] + Enter 取消: ").strip().lower()
        if ans == "q":
            fail("用户取消")
            return False
        screen = ctrl.screenshot()
        if checker(screen):
            ok(f"确认在目标页面: {page_name}")
            return True
        warn(f"当前不在 [{page_name}]，请继续切换...")


# ═══════════════════════════════════════════════════════════════════════════════
# 命令行参数解析
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class E2EArgs:
    """e2e 测试命令行参数。"""

    serial: str | None
    auto: bool
    debug: bool
    pause: float
    log_dir: Path
    log_level: str


def parse_e2e_args(
    test_name: str,
    precondition: str = "",
    *,
    default_log_dir: str = "logs/e2e",
    default_pause: float = 1.5,
) -> E2EArgs:
    """解析 e2e 测试的命令行参数并打印欢迎信息。

    Parameters
    ----------
    test_name:
        测试名称，显示在欢迎头部。
    precondition:
        前置条件说明，打印给用户看。
    default_log_dir:
        默认日志目录。
    default_pause:
        默认每步等待时间 (秒)。

    Returns
    -------
    E2EArgs
        解析后的参数对象。
    """
    serial: str | None = None
    auto = False
    debug = False
    pause = default_pause

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--auto":
            auto = True
        elif arg == "--debug":
            debug = True
        elif arg == "--pause":
            i += 1
            pause = float(args[i])
        elif not arg.startswith("-"):
            serial = arg
        i += 1

    log_dir = Path(default_log_dir)
    log_level = "DEBUG" if debug else "INFO"
    mode_label = "自动" if auto else "交互"

    _print_header(f"AutoWSGR — {test_name} ({mode_label}模式)")
    print()
    print(f"  设备    : {serial or '自动检测'}")
    print(f"  模式    : {mode_label}")
    print(f"  动作间隔: {pause:.1f}s")
    print(f"  日志目录: {log_dir.resolve()}")
    if precondition:
        print()
        print(f"  前置条件: {precondition}")
    print()

    return E2EArgs(
        serial=serial,
        auto=auto,
        debug=debug,
        pause=pause,
        log_dir=log_dir,
        log_level=log_level,
    )


def connect_device(serial: str | None, *, timeout: float = 15.0) -> "ADBController":
    """创建并连接 ADB 控制器，失败时退出进程。"""
    from autowsgr.emulator import ADBController

    ctrl = ADBController(serial=serial, screenshot_timeout=timeout)
    try:
        dev_info = ctrl.connect()
        ok(f"已连接: {dev_info.serial}  分辨率: {dev_info.resolution[0]}x{dev_info.resolution[1]}")
    except Exception as exc:
        fail(f"连接失败: {exc}")
        sys.exit(1)
    return ctrl
