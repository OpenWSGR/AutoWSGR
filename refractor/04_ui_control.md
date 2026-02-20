# UI 控制层 (UIControl) — 核心设计

## 核心理念

**每个 UI 页面有对应的 Controller**。Controller 知道：
1. **如何识别**自己（该页面的视觉特征）
2. **该页面能做什么操作**（读取信息、点击按钮等）
3. **如何导航到相邻页面**（通过 UIAction）

```
UIRecognizer  ─截图→  识别当前页面  ─→  返回对应 Controller
                                        │
UIController  ─持有→  多个 UIAction  ─→  导航到下一页面
                                        │
UIAction      ─执行→  点击/等待/重试  ─→  成功: 新 Controller
                                        └→  失败: 由 Controller 处理
```

---

## 1. UIAction（不对外暴露）

UIAction 定义了一次页面转换操作。它是内部组件，上层不直接使用。

```python
# autowsgr/ui/action.py

from dataclasses import dataclass, field
from typing import Callable
import time
import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.vision.matcher import ImageMatcher, MatchResult, Color
from autowsgr.infra import ActionFailedError


@dataclass(frozen=True)
class ClickStep:
    """一次点击"""
    x: int
    y: int
    delay_after: float = 0.3    # 点击后等待


@dataclass(frozen=True)
class SwipeStep:
    """一次滑动"""
    x1: int
    y1: int
    x2: int
    y2: int
    duration: float = 0.5
    delay_after: float = 0.3


@dataclass
class UIAction:
    """页面切换操作
    
    定义了从当前页面导航到目标页面的具体步骤。
    Action 可能失败（点击后未到达预期页面），由持有它的 Controller 处理。
    """
    
    name: str                           # 操作名称（调试用）
    target_page: str                    # 目标页面名
    steps: list[ClickStep | SwipeStep]  # 操作步骤
    alternative_targets: list[str] = field(default_factory=list)  # 可能到达的其他页面
    
    def execute(
        self,
        device: AndroidController,
        delay: float = 0.3,
    ) -> None:
        """执行操作步骤（不负责验证结果）"""
        for step in self.steps:
            if isinstance(step, ClickStep):
                device.click(step.x, step.y)
                time.sleep(step.delay_after)
            elif isinstance(step, SwipeStep):
                device.swipe(step.x1, step.y1, step.x2, step.y2, step.duration)
                time.sleep(step.delay_after)
        time.sleep(delay)
```

---

## 2. UIController（每页一个）

```python
# autowsgr/ui/controller.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import time
import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.vision.matcher import ImageMatcher, Color
from autowsgr.vision.ocr import OCREngine
from autowsgr.infra import ActionFailedError, NavigationError

if TYPE_CHECKING:
    from autowsgr.ui.recognizer import UIRecognizer


class UIController(ABC):
    """UI 页面控制器基类
    
    每个游戏页面对应一个 Controller 子类。
    Controller 在走到该页面时创建并初始化（通过 UIRecognizer）。
    """
    
    # 子类必须定义
    PAGE_NAME: str = ""
    
    def __init__(
        self,
        device: AndroidController,
        matcher: ImageMatcher,
        ocr: OCREngine,
        recognizer: UIRecognizer,
        screen: np.ndarray,
    ) -> None:
        self._device = device
        self._matcher = matcher
        self._ocr = ocr
        self._recognizer = recognizer
        self._screen: np.ndarray = screen       # 创建时的截图
        self._actions: dict[str, UIAction] = {}
        
        self._register_actions()
    
    @abstractmethod
    def _register_actions(self) -> None:
        """注册本页面可用的 UIAction（导航到其他页面）"""
        ...
    
    @abstractmethod
    def identify(self, screen: np.ndarray) -> bool:
        """判断给定截图是否是本页面"""
        ...
    
    # ── 导航 ──
    
    def navigate_to(self, target_page: str) -> UIController:
        """导航到目标页面，返回目标页面的 Controller
        
        如果本页面直接有到目标页面的 Action，执行它。
        否则由上层（路由器或游戏操作层）规划路径。
        """
        action = self._actions.get(target_page)
        if action is None:
            raise NavigationError(self.PAGE_NAME, target_page, "无直接导航路径")
        
        action.execute(self._device)
        
        # 等待并识别新页面
        new_controller = self._wait_for_page(
            expected=[action.target_page] + action.alternative_targets,
            timeout=10.0,
        )
        return new_controller
    
    def _wait_for_page(
        self,
        expected: list[str],
        timeout: float = 10.0,
        interval: float = 0.3,
    ) -> UIController:
        """等待到达预期页面之一"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            screen = self._device.screenshot()
            controller = self._recognizer.recognize(screen, candidates=expected)
            if controller is not None:
                return controller
            time.sleep(interval)
        
        raise NavigationError(
            self.PAGE_NAME,
            "/".join(expected),
            f"等待超时 {timeout}s",
        )
    
    # ── 便捷方法（子类通用） ──
    
    def refresh_screen(self) -> np.ndarray:
        """刷新截图"""
        self._screen = self._device.screenshot()
        return self._screen
    
    def click(self, x: int, y: int, delay: float = 0.3) -> None:
        self._device.click(x, y)
        time.sleep(delay)
    
    def check_pixel(self, x: int, y: int, expected: Color, tolerance: float = 20.0) -> bool:
        return self._matcher.check_pixel(self._screen, x, y, expected, tolerance)
    
    @property
    def available_targets(self) -> list[str]:
        """可直接导航到的页面列表"""
        return list(self._actions.keys())
```

---

## 3. 具体 Controller 示例

### MainPageController — 主页

```python
# autowsgr/ui/pages/main_page.py

from autowsgr.ui.controller import UIController
from autowsgr.ui.action import UIAction, ClickStep
from autowsgr.vision.templates import PageTemplate


class MainPageController(UIController):
    PAGE_NAME = "main_page"
    
    def _register_actions(self) -> None:
        self._actions = {
            "map_page": UIAction(
                name="出征",
                target_page="map_page",
                steps=[ClickStep(900, 480)],
                alternative_targets=["expedition_page"],
            ),
            "mission_page": UIAction(
                name="任务",
                target_page="mission_page",
                steps=[ClickStep(656, 480)],
            ),
            "backyard_page": UIAction(
                name="后院",
                target_page="backyard_page",
                steps=[ClickStep(45, 80)],
            ),
            "options_page": UIAction(
                name="工厂",
                target_page="options_page",
                steps=[ClickStep(42, 484)],
            ),
        }
    
    def identify(self, screen: np.ndarray) -> bool:
        # 匹配主页标识图片，排除 options_page
        tpl = self._recognizer.templates.get(PageTemplate.MAIN_PAGE)
        if not self._matcher.match(screen, tpl):
            return False
        # 排除: options_page 也能匹配到 main_page 的部分元素
        tpl_options = self._recognizer.templates.get(PageTemplate.OPTIONS_PAGE)
        if self._matcher.match(screen, tpl_options):
            return False
        return True
    
    # ── 主页特有操作 ──
    
    def get_resources(self) -> dict[str, int]:
        """读取四项资源"""
        self.refresh_screen()
        resources = {}
        # OCR 识别四个资源区域
        crop_regions = {
            "fuel":  (65, 15, 175, 35),
            "ammo":  (195, 15, 305, 35),
            "steel": (325, 15, 435, 35),
            "bauxite": (455, 15, 565, 35),
        }
        for name, (x1, y1, x2, y2) in crop_regions.items():
            cropped = self._matcher.crop(self._screen, x1, y1, x2, y2)
            value = self._ocr.recognize_number(cropped, extra_chars="KM.")
            resources[name] = value or 0
        return resources
    
    def has_expedition_return(self) -> bool:
        """检查是否有远征返回"""
        self.refresh_screen()
        # 像素检查或图像匹配
        ...
```

### FightPrepareController — 出击准备页

```python
# autowsgr/ui/pages/fight_prepare.py

from autowsgr.ui.controller import UIController
from autowsgr.ui.action import UIAction, ClickStep
from autowsgr.vision.matcher import Color


FLEET_TAB_POSITIONS = [(64, 83), (186, 83), (310, 83), (430, 83)]
FLEET_TAB_ACTIVE_COLOR = Color.from_bgr((228, 132, 16))
BLOOD_BAR_POSITIONS = [(56, 322), (168, 322), (280, 322), (392, 322), (504, 322), (616, 322)]


class FightPrepareController(UIController):
    PAGE_NAME = "fight_prepare_page"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 页面特有状态
        self._current_fleet_id: int | None = None
    
    def _register_actions(self) -> None:
        self._actions = {
            "map_page": UIAction(
                name="返回地图",
                target_page="map_page",
                steps=[ClickStep(30, 30)],
            ),
            # 开始出征不是导航到新"页面"，而是进入战斗流程
            # 所以不作为 UIAction，而是专用方法
        }
    
    def identify(self, screen: np.ndarray) -> bool:
        tpl = self._recognizer.templates.get(PageTemplate.FIGHT_PREPARE)
        return bool(self._matcher.match(screen, tpl))
    
    # ── 页面特有操作 ──
    
    def get_current_fleet_id(self) -> int:
        """识别当前选中的舰队编号 (1-4)"""
        self.refresh_screen()
        for i, (x, y) in enumerate(FLEET_TAB_POSITIONS):
            if self.check_pixel(x, y, FLEET_TAB_ACTIVE_COLOR):
                self._current_fleet_id = i + 1
                return i + 1
        return 1  # 默认
    
    def switch_fleet(self, fleet_id: int) -> None:
        """切换到指定舰队"""
        if fleet_id < 1 or fleet_id > 4:
            raise ValueError(f"舰队编号必须 1-4, 收到 {fleet_id}")
        x, y = FLEET_TAB_POSITIONS[fleet_id - 1]
        self.click(x, y)
        self._current_fleet_id = fleet_id
    
    def detect_ship_damage(self) -> list[int]:
        """检测 6 个位置的舰船血量状态
        
        Returns: [0]*7, index 0 unused, 1-6 对应每个位置
                 0=健康, 1=小破, 2=中破, 3=大破, -1=空位
        """
        self.refresh_screen()
        result = [0] * 7
        for i, (x, y) in enumerate(BLOOD_BAR_POSITIONS, start=1):
            pixel = self._matcher.get_pixel(self._screen, x, y)
            result[i] = _classify_damage(pixel)
        return result
    
    def start_sortie(self) -> None:
        """点击出击按钮"""
        self.click(900, 500)
    
    def quick_repair(self, positions: list[int]) -> None:
        """对指定位置快修"""
        self.click(420, 420)  # 打开快修面板
        time.sleep(0.5)
        for pos in positions:
            x, y = BLOOD_BAR_POSITIONS[pos - 1]
            self.click(x, y)
        # 确认
        ...
    
    def supply(self, positions: list[int] | None = None) -> None:
        """补给"""
        self.click(293, 420)  # 补给按钮
        time.sleep(0.3)
        if positions is None:
            # 全部补给
            self.click(180, 420)
        else:
            for pos in positions:
                self.click(110 * pos, 241)
        ...


def _classify_damage(pixel: Color) -> int:
    """根据血条颜色判断破损程度"""
    # 绿色=健康, 黄色=小破, 橙色=中破, 红色=大破
    damage_colors = {
        0: Color.from_bgr((0, 200, 0)),    # 健康
        1: Color.from_bgr((0, 200, 200)),   # 小破 
        2: Color.from_bgr((0, 128, 255)),   # 中破
        3: Color.from_bgr((0, 0, 200)),     # 大破
    }
    min_dist = float("inf")
    result = -1
    for level, color in damage_colors.items():
        d = pixel.distance(color)
        if d < min_dist:
            min_dist = d
            result = level
    return result if min_dist < 80 else -1
```

### 更多 Controller（列举关键页面）

| Controller | PAGE_NAME | 关键能力 | Actions |
|-----------|-----------|---------|---------|
| `MapPageController` | `map_page` | 选章节、选地图 | → fight_prepare, exercise, expedition, battle |
| `ExercisePageController` | `exercise_page` | 检测对手状态、选择 | → map_page (顶栏互通) |
| `ExpeditionPageController` | `expedition_page` | 收远征、派遣 | → map_page |
| `BattlePageController` | `battle_page` | 选择战役 | → map_page |
| `BuildPageController` | `build_page` | 建造、收船 | → options → main |
| `CanteenPageController` | `canteen_page` | 做菜/喂菜 | → backyard → main |
| `BathPageController` | `bath_page` | 入浴修理 | → backyard → main |
| `ChooseShipPageController` | `choose_ship_page` | 搜索/选择船 | → fight_prepare |
| `DestroyPageController` | `destroy_page` | 解装 | → options → main |

---

## 4. UIRecognizer

```python
# autowsgr/ui/recognizer.py

from __future__ import annotations
import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.vision.matcher import ImageMatcher, Color
from autowsgr.vision.ocr import OCREngine
from autowsgr.vision.templates import PageTemplate, TemplateRegistry


class UIRecognizer:
    """UI 页面识别器
    
    给定一张截图，识别当前是哪个页面，并返回对应的 Controller。
    """
    
    def __init__(
        self,
        device: AndroidController,
        matcher: ImageMatcher,
        ocr: OCREngine,
    ) -> None:
        self._device = device
        self._matcher = matcher
        self._ocr = ocr
        self.templates = TemplateRegistry()
        
        # 注册所有 Controller 类
        self._controllers: dict[str, type[UIController]] = {}
        self._register_all()
    
    def _register_all(self) -> None:
        """注册所有页面 Controller"""
        from autowsgr.ui.pages import (
            MainPageController,
            MapPageController,
            FightPrepareController,
            ExercisePageController,
            ExpeditionPageController,
            BattlePageController,
            BuildPageController,
            CanteenPageController,
            BathPageController,
            ChooseShipPageController,
            DestroyPageController,
            OptionsPageController,
            MissionPageController,
            BackyardPageController,
            DecisiveBattleController,
            # ...
        )
        for cls in [
            MainPageController, MapPageController, FightPrepareController,
            ExercisePageController, ExpeditionPageController, BattlePageController,
            BuildPageController, CanteenPageController, BathPageController,
            ChooseShipPageController, DestroyPageController, OptionsPageController,
            MissionPageController, BackyardPageController, DecisiveBattleController,
        ]:
            self._controllers[cls.PAGE_NAME] = cls
    
    def recognize(
        self,
        screen: np.ndarray | None = None,
        candidates: list[str] | None = None,
    ) -> UIController | None:
        """识别当前页面并返回对应的 Controller
        
        Args:
            screen: 截图。为 None 则自动截图。
            candidates: 限定候选页面列表（提高效率）。为 None 则遍历全部。
        
        Returns:
            对应的 UIController 实例，识别失败返回 None。
        """
        if screen is None:
            screen = self._device.screenshot()
        
        controllers_to_check = (
            {name: self._controllers[name] for name in candidates if name in self._controllers}
            if candidates
            else self._controllers
        )
        
        for name, ctrl_cls in controllers_to_check.items():
            # 创建临时实例做识别
            ctrl = ctrl_cls(
                device=self._device,
                matcher=self._matcher,
                ocr=self._ocr,
                recognizer=self,
                screen=screen,
            )
            if ctrl.identify(screen):
                logger.debug("识别页面: {}", name)
                return ctrl
        
        return None
    
    def wait_for_page(
        self,
        targets: list[str],
        timeout: float = 10.0,
        interval: float = 0.3,
    ) -> UIController:
        """等待到达目标页面之一"""
        import time
        from autowsgr.infra import PageNotFoundError
        
        deadline = time.time() + timeout
        while time.time() < deadline:
            screen = self._device.screenshot()
            ctrl = self.recognize(screen, candidates=targets)
            if ctrl is not None:
                return ctrl
            time.sleep(interval)
        
        raise PageNotFoundError(f"等待页面超时: {targets}")
    
    def take_screenshot_and_recognize(self) -> UIController | None:
        """截图 + 识别，快捷方法"""
        return self.recognize()
```

**关于 identify 的性能优化：**

当前代码遍历 ~30 个页面依次匹配，代价较高。优化策略：
1. **候选列表**：多数场景知道可能到达哪些页面，传 `candidates` 限定范围
2. **快速排除**：先做像素检查（极快），排除不可能的页面
3. **互通组**：顶栏标签页组共享顶栏特征，先判断是否在标签页组，再区分具体页面

```python
# 互通组优化示例
INTEGRATIVE_TAB_POSITIONS = [(171, 47), (300, 47), (393, 47), (504, 47), (659, 47)]
TAB_ACTIVE_COLOR = Color.from_bgr((225, 130, 16))

def _identify_tab_group(screen: np.ndarray, matcher: ImageMatcher) -> int | None:
    """识别顶栏标签页组的当前活跃标签 (1-5)"""
    for i, (x, y) in enumerate(INTEGRATIVE_TAB_POSITIONS):
        if matcher.check_pixel(screen, x, y, TAB_ACTIVE_COLOR):
            return i + 1
    return None
```

---

## 5. 路由器 — 跨页面导航

单个 Controller 只知道直接相邻的页面。跨多页导航需要路由器：

```python
# autowsgr/ui/router.py

from loguru import logger
from autowsgr.ui.controller import UIController
from autowsgr.ui.recognizer import UIRecognizer
from autowsgr.infra import NavigationError


# 页面邻接表（从 UI 树退化为静态配置）
ADJACENCY: dict[str, list[str]] = {
    "main_page":         ["map_page", "mission_page", "backyard_page", "options_page"],
    "map_page":          ["main_page", "fight_prepare_page", "exercise_page", "expedition_page", "battle_page", "decisive_battle_entrance"],
    "exercise_page":     ["map_page", "expedition_page", "battle_page", "decisive_battle_entrance"],
    "expedition_page":   ["map_page", "exercise_page", "battle_page", "decisive_battle_entrance"],
    "battle_page":       ["map_page", "exercise_page", "expedition_page", "decisive_battle_entrance"],
    "fight_prepare_page":["map_page"],
    "mission_page":      ["main_page"],
    "backyard_page":     ["main_page", "bath_page", "canteen_page"],
    "bath_page":         ["backyard_page", "choose_repair_page"],
    "canteen_page":      ["backyard_page"],
    "options_page":      ["main_page", "build_page", "intensify_page", "friend_page"],
    "build_page":        ["options_page", "destroy_page", "develop_page", "discard_page"],
    "destroy_page":      ["build_page", "develop_page", "discard_page"],
    # ...
}

# 每个页面的"返回"目标
PARENT_PAGE: dict[str, str] = {
    "map_page": "main_page",
    "mission_page": "main_page",
    "backyard_page": "main_page",
    "options_page": "main_page",
    "fight_prepare_page": "map_page",
    "bath_page": "backyard_page",
    "canteen_page": "backyard_page",
    "build_page": "options_page",
    # ...
}


def find_route(source: str, target: str) -> list[str]:
    """BFS 找最短路径"""
    from collections import deque
    
    if source == target:
        return [source]
    
    queue = deque([(source, [source])])
    visited = {source}
    
    while queue:
        current, path = queue.popleft()
        for neighbor in ADJACENCY.get(current, []):
            if neighbor == target:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    
    raise NavigationError(source, target, "无可达路径")


def navigate(
    recognizer: UIRecognizer,
    current: UIController,
    target_page: str,
) -> UIController:
    """多跳导航：从当前页面走到任意目标页面"""
    if current.PAGE_NAME == target_page:
        return current
    
    route = find_route(current.PAGE_NAME, target_page)
    logger.info("导航路径: {}", " → ".join(route))
    
    controller = current
    for next_page in route[1:]:
        controller = controller.navigate_to(next_page)
    
    return controller


def go_main_page(recognizer: UIRecognizer) -> UIController:
    """无论当前在哪，回到主页面
    
    策略：反复点击返回按钮直到识别出 main_page。
    不依赖任何页面状态。
    """
    import time
    from autowsgr.vision.templates import SymbolTemplate
    
    BACK_BUTTON_POSITIONS = [(30, 30), (33, 30), (50, 30)]
    
    for attempt in range(20):
        ctrl = recognizer.take_screenshot_and_recognize()
        if ctrl is not None and ctrl.PAGE_NAME == "main_page":
            return ctrl
        
        # 尝试点击返回按钮
        screen = recognizer._device.screenshot()
        # 先尝试匹配返回按钮图标
        # 如果没有，尝试固定位置点击
        for x, y in BACK_BUTTON_POSITIONS:
            recognizer._device.click(x, y)
            time.sleep(0.8)
            break
    
    raise NavigationError("unknown", "main_page", "20次重试后仍未到达主页")
```

---

## 6. 设计核心总结

### Controller 生命周期

```
1. UIRecognizer.recognize(screen) 
   → 遍历已注册的 Controller 类
   → 调用 ctrl.identify(screen) 
   → 首个返回 True 的 → 实例化并返回

2. controller.navigate_to("target_page")
   → 查找 _actions["target_page"]
   → action.execute(device)  
   → 等待并识别新页面 → 返回新 Controller

3. 旧 Controller 自然丢弃（无需显式销毁）
```

### 与现有代码的映射

| 现有代码 | 新设计 |
|---------|--------|
| `WSGR_UI` 全局单例 + `Node` + `Edge` | `UIController` + `UIAction` + `ADJACENCY` |
| `timer.now_page` 全局状态 | 当前持有的 `UIController` 实例即代表当前页面 |
| `timer.identify_page(name)` | `controller.identify(screen)` |
| `timer.get_now_page()` 遍历 | `recognizer.recognize()` |
| `timer.operate(end)` | `router.navigate(recognizer, current, target)` |
| `timer.walk_to(end)` | `router.navigate()` + 错误恢复 |
| `timer.go_main_page()` | `router.go_main_page(recognizer)` |
| `timer.wait_pages(names)` | `recognizer.wait_for_page(targets)` |
| `SwitchMethod` | `UIAction` + `ClickStep` |
| `Edge.other_dst` | `UIAction.alternative_targets` |

### 关键改进

1. **状态即对象**：当前页面 = 当前持有的 Controller 实例。不再维护 `now_page` 字符串
2. **Action 可失败**：`UIAction.execute()` 后需验证是否到达目标。失败由 Controller 决定重试/回退
3. **每页独立**：每个 Controller 封装自己的坐标、识别逻辑和特有操作
4. **可测试**：Controller 不依赖全局状态，mock AndroidController 即可单元测试
