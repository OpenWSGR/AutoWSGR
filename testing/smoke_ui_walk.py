"""全面 UI 游走端到端测试 — 遍历所有可达页面并记录截图。

运行方式::

    # 交互模式 (默认): 每步需人类确认
    python testing/smoke_ui_walk.py

    # 非交互模式: 全自动执行
    python testing/smoke_ui_walk.py --auto

    # 指定设备
    python testing/smoke_ui_walk.py emulator-5554

    # 完整参数
    python testing/smoke_ui_walk.py emulator-5554 --auto --debug --pause 2.0

前置条件：
    1. 模拟器已启动
    2. 游戏已打开并位于 **主页面** (母港/秘书舰界面)

测试设计：
    本测试从主页面出发，按深度优先遍历所有 UI 导航边，覆盖:

    1. 前向导航 — 主页面出发到达所有 11 个注册页面
    2. 回退导航 — 每个子页面通过 go_back/close 返回父页面
    3. 标签切换 — 建造 (4 标签)、强化 (3 标签) 页面内标签切换
    4. 页面识别 — 每步截图并用 is_current_page 验证
    5. 全局识别 — 每步用 get_current_page 确认注册表一致性

    测试路径 (欧拉遍历):

    主页面
    ├── → 出征 → 地图页面 (5面板切换: 出征→演习→远征→战役→决战→出征) → ◁ 主页面
    ├── → 任务 → 任务页面 → ◁ 主页面
    ├── → 后院 → 后院页面
    │   ├── → 浴室 → 浴室页面 → ◁ 后院页面
    │   ├── → 食堂 → 食堂页面 → ◁ 后院页面
    │   └── ◁ 主页面
    └── → 侧边栏
        ├── → 建造 → 建造页面 (4标签) → ◁ 侧边栏
        ├── → 强化 → 强化页面 (3标签) → ◁ 侧边栏
        ├── → 好友 → 好友页面 → ◁ 侧边栏
        └── close → 主页面

    共 22 个导航步骤 + 7 个标签切换 + 5 个面板切换 = 34 个操作步骤。

截图输出：
    logs/smoke_walk/images/ 目录下，每步一张截图，命名格式:
    {步骤序号:03d}_{动作描述}_{时间戳}.png

    这些截图可直接用于后续集成测试的 mock 数据源。
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

if TYPE_CHECKING:
    from collections.abc import Callable

# ── 把项目根目录加入 path ──
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from autowsgr.emulator.controller import ADBController
from autowsgr.infra.logger import save_image, setup_logger
from autowsgr.ui.page import get_current_page, get_registered_pages


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
class WalkReport:
    """遍历报告。"""

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
# 配置
# ═══════════════════════════════════════════════════════════════════════════════

LOG_DIR = Path("logs/smoke_walk")
DEFAULT_PAUSE = 1.5  # 导航动作后等待 UI 动画完成 (秒)


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


class _Symbols:
    OK = "✓"
    FAIL = "✗"
    INFO = "ℹ"
    WARN = "⚠"


def _ok(msg: str) -> None:
    print(f"  {_Symbols.OK} {msg}")


def _fail(msg: str) -> None:
    print(f"  {_Symbols.FAIL} {msg}")


def _info(msg: str) -> None:
    print(f"  {_Symbols.INFO} {msg}")


def _warn(msg: str) -> None:
    print(f"  {_Symbols.WARN} {msg}")


def _prompt_step(index: int, action: str, auto_mode: bool) -> str:
    """显示步骤提示并获取用户指令。

    Returns
    -------
    str
        ``"run"`` / ``"skip"`` / ``"quit"``
    """
    _print_step(index, action)
    if auto_mode:
        return "run"
    ans = input("  [Enter] 执行  |  [s] 跳过  |  [q] 退出: ").strip().lower()
    if ans == "q":
        return "quit"
    return "skip" if ans == "s" else "run"


# ═══════════════════════════════════════════════════════════════════════════════
# 核心: 步骤执行器
# ═══════════════════════════════════════════════════════════════════════════════


class UIWalkRunner:
    """UI 游走测试执行器。"""

    def __init__(
        self,
        ctrl: ADBController,
        *,
        auto_mode: bool = False,
        pause: float = DEFAULT_PAUSE,
    ) -> None:
        self.ctrl = ctrl
        self.auto_mode = auto_mode
        self.pause = pause
        self.report = WalkReport(
            mode="auto" if auto_mode else "interactive",
            start_time=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._step_counter = 0
        self._aborted = False

    # ── 截图 + 验证 ─────────────────────────────────────────────────────

    def _take_screenshot(self, tag: str) -> tuple[np.ndarray, Path | None]:
        """截图并保存，返回 (screen, path)。"""
        screen = self.ctrl.screenshot()
        path = save_image(screen, tag=tag)
        return screen, path

    def _verify_page(
        self,
        screen: np.ndarray,
        expected_page: str,
        checker: Callable[[np.ndarray], bool],
    ) -> tuple[bool, str | None]:
        """验证页面是否符合预期。

        Returns (page_check, actual_page_name)。
        """
        page_check = checker(screen)
        actual_page = get_current_page(screen)
        return page_check, actual_page

    # ── 单步执行 ─────────────────────────────────────────────────────────

    def execute_step(
        self,
        action: str,
        expected_page: str,
        checker: Callable[[np.ndarray], bool],
        do_action: Callable[[], None],
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

        # 1. 提示用户
        user_choice = _prompt_step(idx, action, self.auto_mode)
        if user_choice == "quit":
            self._aborted = True
            return None
        if user_choice == "skip":
            rec = StepRecord(index=idx, action=action, expected_page=expected_page, result=StepResult.SKIP)
            self.report.add(rec)
            _info("已跳过")
            return rec

        # 2. 执行动作
        # 文件名安全化: 去除 Windows 非法字符 (: * ? " < > |) 及中文标点
        raw_tag = screenshot_tag or f"{idx:03d}_{action}"
        tag = (
            raw_tag
            .replace(' ', '_')
            .replace('→', 'to')
            .replace('◁', 'back')
            .replace(':', '')
            .replace('：', '')
            .replace('*', '')
            .replace('?', '')
            .replace('"', '')
            .replace('<', '')
            .replace('>', '')
            .replace('|', '')
        )
        rec = StepRecord(index=idx, action=action, expected_page=expected_page)
        t0 = time.monotonic()

        try:
            do_action()
            time.sleep(self.pause)

            # 3. 截图 + 验证
            screen, path = self._take_screenshot(tag)
            rec.screenshot_path = str(path) if path else None
            rec.duration_ms = int((time.monotonic() - t0) * 1000)

            page_check, actual_page = self._verify_page(screen, expected_page, checker)
            rec.page_check = page_check
            rec.actual_page = actual_page

            if page_check:
                rec.result = StepResult.PASS
                _ok(f"页面验证通过: {expected_page}")
                if actual_page and actual_page != expected_page:
                    _warn(f"get_current_page 返回 '{actual_page}' (预期 '{expected_page}')")
            else:
                rec.result = StepResult.FAIL
                _fail(f"页面验证失败: 期望 '{expected_page}', 实际 '{actual_page or '未知'}'")

        except Exception as exc:
            rec.result = StepResult.ERROR
            rec.error_msg = str(exc)
            rec.duration_ms = int((time.monotonic() - t0) * 1000)
            _fail(f"执行异常: {exc}")

            # 异常后尝试截图保留现场
            try:
                _, path = self._take_screenshot(f"{tag}_error")
                rec.screenshot_path = str(path) if path else None
            except Exception:
                pass

        self.report.add(rec)
        return rec

    # ── 纯验证步骤 (无动作) ──────────────────────────────────────────────

    def verify_current(
        self,
        action: str,
        expected_page: str,
        checker: Callable[[np.ndarray], bool],
    ) -> StepRecord | None:
        """只截图验证当前页面，不执行任何动作。"""
        return self.execute_step(
            action=action,
            expected_page=expected_page,
            checker=checker,
            do_action=lambda: None,
            screenshot_tag=f"{self._step_counter + 1:03d}_verify_{expected_page.replace(' ', '_')}",
        )

    # ── 报告 ─────────────────────────────────────────────────────────────

    @property
    def aborted(self) -> bool:
        return self._aborted

    def finalize(self) -> WalkReport:
        """完成报告并保存 JSON。"""
        self.report.end_time = datetime.now(tz=timezone.utc).isoformat()

        # 保存 JSON 报告
        report_dir = LOG_DIR
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "walk_report.json"

        # 序列化
        data = {
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
        _info(f"报告已保存: {report_path.resolve()}")

        return self.report

    def print_summary(self) -> None:
        """打印测试结果汇总。"""
        r = self.report
        _print_header("UI 游走测试结果汇总")
        print()

        # 逐步结果
        for s in r.steps:
            icon = {
                StepResult.PASS: _Symbols.OK,
                StepResult.FAIL: _Symbols.FAIL,
                StepResult.SKIP: "○",
                StepResult.ERROR: _Symbols.WARN,
            }[s.result]
            duration = f"{s.duration_ms}ms" if s.duration_ms else ""
            page_info = f"  [{s.actual_page or '?'}]" if s.result != StepResult.SKIP else ""
            print(f"  {icon} [{s.index:03d}] {s.action:<40s} {s.result.value:5s} {duration:>8s}{page_info}")

        print()
        print(f"  总计: {r.total_steps} 步")
        print(f"  通过: {r.passed}  失败: {r.failed}  跳过: {r.skipped}  异常: {r.errors}")
        print()

        if r.failed == 0 and r.errors == 0:
            _ok("全部通过!")
        else:
            _fail(f"存在 {r.failed} 个失败 + {r.errors} 个异常")

        print(f"  截图目录: {(LOG_DIR / 'images').resolve()}")
        print(f"  报告文件: {(LOG_DIR / 'walk_report.json').resolve()}")
        print("═" * 68)


# ═══════════════════════════════════════════════════════════════════════════════
# 测试路径: 所有导航步骤
# ═══════════════════════════════════════════════════════════════════════════════


def run_walk(runner: UIWalkRunner) -> None:
    """执行完整 UI 游走路径。"""
    ctrl = runner.ctrl

    # ── 延迟导入页面控制器 (避免循环导入) ───────────────────────────────
    from autowsgr.ui.backyard_page import BackyardPage, BackyardTarget
    from autowsgr.ui.bath_page import BathPage
    from autowsgr.ui.build_page import BuildPage, BuildTab
    from autowsgr.ui.canteen_page import CanteenPage
    from autowsgr.ui.friend_page import FriendPage
    from autowsgr.ui.intensify_page import IntensifyPage, IntensifyTab
    from autowsgr.ui.main_page import MainPage, MainPageTarget
    from autowsgr.ui.map_page import MapPage, MapPanel
    from autowsgr.ui.mission_page import MissionPage
    from autowsgr.ui.sidebar_page import SidebarPage, SidebarTarget

    # 构建页面实例
    main_page = MainPage(ctrl)
    map_page = MapPage(ctrl)
    backyard_page = BackyardPage(ctrl)
    bath_page = BathPage(ctrl)
    canteen_page = CanteenPage(ctrl)
    sidebar_page = SidebarPage(ctrl)
    build_page = BuildPage(ctrl)
    intensify_page = IntensifyPage(ctrl)
    friend_page = FriendPage(ctrl)
    mission_page = MissionPage(ctrl)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 0: 验证初始状态 — 主页面
    # ═══════════════════════════════════════════════════════════════════
    runner.verify_current(
        "初始验证: 主页面",
        "主页面",
        MainPage.is_current_page,
    )
    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════
    # 路径 A: 主页面 → 出征 → 地图页面 (5面板切换) → ◁ 主页面
    # ═══════════════════════════════════════════════════════════════════

    runner.execute_step(
        "主页面 → 地图页面 (出征)",
        "地图页面",
        MapPage.is_current_page,
        lambda: main_page.navigate_to(MainPageTarget.SORTIE),
    )
    if runner.aborted:
        return

    # 地图 5 面板切换: 演习 → 远征 → 战役 → 决战 → 出征(回到初始)
    for panel in [MapPanel.EXERCISE, MapPanel.EXPEDITION, MapPanel.BATTLE, MapPanel.DECISIVE, MapPanel.SORTIE]:
        runner.execute_step(
            f"地图页面: 切换面板 → {panel.value}",
            "地图页面",
            MapPage.is_current_page,
            lambda p=panel: map_page.switch_panel(p),
        )
        if runner.aborted:
            return

    runner.execute_step(
        "地图页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: map_page.go_back(),
    )
    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════
    # 路径 B: 主页面 → 任务 → 任务页面 → ◁ 主页面
    # ═══════════════════════════════════════════════════════════════════

    runner.execute_step(
        "主页面 → 任务页面",
        "任务页面",
        MissionPage.is_current_page,
        lambda: main_page.navigate_to(MainPageTarget.TASK),
    )
    if runner.aborted:
        return

    runner.execute_step(
        "任务页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: mission_page.go_back(),
    )
    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════
    # 路径 C: 主页面 → 后院 → 浴室 → ◁ 后院 → 食堂 → ◁ 后院 → ◁ 主页面
    # ═══════════════════════════════════════════════════════════════════

    runner.execute_step(
        "主页面 → 后院页面",
        "后院页面",
        BackyardPage.is_current_page,
        lambda: main_page.navigate_to(MainPageTarget.HOME),
    )
    if runner.aborted:
        return

    # 后院 → 浴室
    runner.execute_step(
        "后院页面 → 浴室页面",
        "浴室页面",
        BathPage.is_current_page,
        lambda: backyard_page.navigate_to(BackyardTarget.BATH),
    )
    if runner.aborted:
        return

    # 浴室 → ◁ 后院
    runner.execute_step(
        "浴室页面 → ◁ 后院页面",
        "后院页面",
        BackyardPage.is_current_page,
        lambda: bath_page.go_back(),
    )
    if runner.aborted:
        return

    # 后院 → 食堂
    runner.execute_step(
        "后院页面 → 食堂页面",
        "食堂页面",
        CanteenPage.is_current_page,
        lambda: backyard_page.navigate_to(BackyardTarget.CANTEEN),
    )
    if runner.aborted:
        return

    # 食堂 → ◁ 后院
    runner.execute_step(
        "食堂页面 → ◁ 后院页面",
        "后院页面",
        BackyardPage.is_current_page,
        lambda: canteen_page.go_back(),
    )
    if runner.aborted:
        return

    # 后院 → ◁ 主页面
    runner.execute_step(
        "后院页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: backyard_page.go_back(),
    )
    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════
    # 路径 D: 主页面 → 侧边栏
    #   → 建造 (4标签) → ◁ 侧边栏
    #   → 强化 (3标签) → ◁ 侧边栏
    #   → 好友 → ◁ 侧边栏
    #   → close → 主页面
    # ═══════════════════════════════════════════════════════════════════

    runner.execute_step(
        "主页面 → 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: main_page.navigate_to(MainPageTarget.SIDEBAR),
    )
    if runner.aborted:
        return

    # ── 侧边栏 → 建造 ─────────────────────────────────────────────

    runner.execute_step(
        "侧边栏 → 建造页面",
        "建造页面",
        BuildPage.is_current_page,
        lambda: sidebar_page.navigate_to(SidebarTarget.BUILD),
    )
    if runner.aborted:
        return

    # 建造 4 标签切换
    for tab in [BuildTab.DESTROY, BuildTab.DEVELOP, BuildTab.DISCARD, BuildTab.BUILD]:
        runner.execute_step(
            f"建造页面: 切换标签 → {tab.value}",
            "建造页面",
            BuildPage.is_current_page,
            lambda t=tab: build_page.switch_tab(t),
        )
        if runner.aborted:
            return

    # 建造 → ◁ 侧边栏
    runner.execute_step(
        "建造页面 → ◁ 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: build_page.go_back(),
    )
    if runner.aborted:
        return

    # ── 侧边栏 → 强化 ─────────────────────────────────────────────

    runner.execute_step(
        "侧边栏 → 强化页面",
        "强化页面",
        IntensifyPage.is_current_page,
        lambda: sidebar_page.navigate_to(SidebarTarget.INTENSIFY),
    )
    if runner.aborted:
        return

    # 强化 3 标签切换
    for tab in [IntensifyTab.REMAKE, IntensifyTab.SKILL, IntensifyTab.INTENSIFY]:
        runner.execute_step(
            f"强化页面: 切换标签 → {tab.value}",
            "强化页面",
            IntensifyPage.is_current_page,
            lambda t=tab: intensify_page.switch_tab(t),
        )
        if runner.aborted:
            return

    # 强化 → ◁ 侧边栏
    runner.execute_step(
        "强化页面 → ◁ 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: intensify_page.go_back(),
    )
    if runner.aborted:
        return

    # ── 侧边栏 → 好友 ─────────────────────────────────────────────

    runner.execute_step(
        "侧边栏 → 好友页面",
        "好友页面",
        FriendPage.is_current_page,
        lambda: sidebar_page.navigate_to(SidebarTarget.FRIEND),
    )
    if runner.aborted:
        return

    # 好友 → ◁ 侧边栏
    runner.execute_step(
        "好友页面 → ◁ 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: friend_page.go_back(),
    )
    if runner.aborted:
        return

    # ── 侧边栏 → close → 主页面 ───────────────────────────────────

    runner.execute_step(
        "侧边栏 → close → 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: sidebar_page.close(),
    )
    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════
    # 最终验证: 回到主页面
    # ═══════════════════════════════════════════════════════════════════
    runner.verify_current(
        "最终验证: 主页面",
        "主页面",
        MainPage.is_current_page,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    # ── 解析参数 ──
    serial: str | None = None
    auto_mode = False
    debug = False
    pause = DEFAULT_PAUSE

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--auto":
            auto_mode = True
        elif arg == "--debug":
            debug = True
        elif arg == "--pause":
            i += 1
            pause = float(args[i])
        elif not arg.startswith("-"):
            serial = arg
        i += 1

    setup_logger(
        log_dir=LOG_DIR,
        level="DEBUG" if debug else "INFO",
        save_images=True,
    )

    from loguru import logger

    mode_label = "自动" if auto_mode else "交互"
    logger.info("=== UI 游走测试开始 (模式: {}) ===", mode_label)

    _print_header(f"AutoWSGR — UI 全面游走测试 ({mode_label}模式)")
    print()
    print(f"  设备    : {serial or '自动检测'}")
    print(f"  模式    : {mode_label}")
    print(f"  动作间隔: {pause:.1f}s")
    print(f"  日志目录: {LOG_DIR.resolve()}")
    print()
    print(f"  已注册页面: {len(get_registered_pages())} 个")
    for name in get_registered_pages():
        print(f"    · {name}")
    print()

    if not auto_mode:
        print("  请确保游戏已打开并位于【主页面】(母港/秘书舰界面)")
        input("  按 Enter 开始 ... ")

    # ── 连接设备 ──────────────────────────────────────────────────────
    ctrl = ADBController(serial=serial, screenshot_timeout=15.0)
    try:
        dev_info = ctrl.connect()
        _ok(f"已连接: {dev_info.serial}  分辨率: {dev_info.resolution[0]}x{dev_info.resolution[1]}")
    except Exception as exc:
        _fail(f"连接失败: {exc}")
        sys.exit(1)

    # ── 执行游走 ──────────────────────────────────────────────────────
    runner = UIWalkRunner(ctrl, auto_mode=auto_mode, pause=pause)

    try:
        run_walk(runner)
    except KeyboardInterrupt:
        _warn("用户中断 (Ctrl+C)")
    except Exception as exc:
        _fail(f"未预期异常: {exc}")
        logger.opt(exception=True).error("游走测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        _ok("设备已断开")

    logger.info("=== UI 游走测试结束 ===")

    # 退出码: 有失败或异常则 exit(1)
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
