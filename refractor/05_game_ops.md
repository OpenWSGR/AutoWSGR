# 游戏操作层 (GameOps)

## 职责

**函数式**地组装 UIController，完成高级游戏操作。

每个函数：
1. 接收当前 Controller + 策略参数
2. 通过 Controller 进行页面操作和导航
3. 返回结果 + 新的 Controller（代表操作后所在的页面）

**不持有状态**，不维护全局 `now_page`。

---

## 设计理念

```python
# 函数签名的通用模式：
def do_something(
    ctrl: UIController,        # 当前页面的 Controller
    recognizer: UIRecognizer,  # 用于导航时识别新页面
    *,                         # 以下为策略参数
    strategy_param: ...,
) -> tuple[UIController, SomeResult]:
    """返回 (操作完成后的 Controller, 操作结果)"""
    ...
```

这种模式的好处：
- **无副作用**：函数不修改全局状态
- **可组合**：一个操作的输出 Controller 是下一个操作的输入
- **可测试**：mock Controller 即可

---

## 1. 出征操作

```python
# autowsgr/ops/sortie.py

from dataclasses import dataclass
from loguru import logger

from autowsgr.ui.controller import UIController
from autowsgr.ui.recognizer import UIRecognizer
from autowsgr.ui.router import navigate, go_main_page
from autowsgr.infra.exceptions import DockFullError, GameError


@dataclass
class SortieConfig:
    """出击配置"""
    chapter: int
    map_id: int
    fleet_id: int = 1
    fleet: list[str] | None = None      # 指定舰队编成
    repair_mode: str = "medium"         # 修理策略


def prepare_sortie(
    ctrl: UIController,
    recognizer: UIRecognizer,
    *,
    config: SortieConfig,
) -> UIController:
    """准备出击：导航到出击准备页面，选章节/地图/舰队
    
    Returns: FightPrepareController
    """
    # 1. 导航到地图页
    ctrl = navigate(recognizer, ctrl, "map_page")
    
    # 2. 选择章节和地图（MapPageController 的能力）
    ctrl.select_chapter(config.chapter)
    ctrl.select_map(config.map_id)
    
    # 3. 进入出击准备页
    ctrl = ctrl.navigate_to("fight_prepare_page")
    
    # 4. 切换舰队
    ctrl.switch_fleet(config.fleet_id)
    
    # 5. 换船（如果指定了舰队编成）
    if config.fleet is not None:
        change_fleet(ctrl, recognizer, fleet=config.fleet)
    
    # 6. 修理
    apply_repair(ctrl, mode=config.repair_mode)
    
    return ctrl


def change_fleet(
    ctrl: UIController,  # FightPrepareController
    recognizer: UIRecognizer,
    *,
    fleet: list[str],
) -> UIController:
    """换船操作"""
    for position, ship_name in enumerate(fleet, start=1):
        if not ship_name:
            continue
        # 点击对应位置 → 进入选船页面
        ctrl.click_ship_slot(position)
        choose_ctrl = recognizer.wait_for_page(["choose_ship_page"])
        
        # 搜索并选择目标舰船
        choose_ctrl.search_ship(ship_name)
        choose_ctrl.select_first()
        
        # 回到出击准备页面
        ctrl = recognizer.wait_for_page(["fight_prepare_page"])
    
    return ctrl


def apply_repair(
    ctrl: UIController,  # FightPrepareController
    *,
    mode: str = "medium",
) -> None:
    """根据策略修理舰船"""
    damage = ctrl.detect_ship_damage()
    positions_to_repair = []
    
    for i in range(1, 7):
        if mode == "always" and damage[i] >= 1:
            positions_to_repair.append(i)
        elif mode == "medium" and damage[i] >= 2:
            positions_to_repair.append(i)
        elif mode == "critical" and damage[i] >= 3:
            positions_to_repair.append(i)
    
    if positions_to_repair:
        ctrl.quick_repair(positions_to_repair)
        logger.info("修理位置: {}", positions_to_repair)
```

---

## 2. 远征操作

```python
# autowsgr/ops/expedition.py

def collect_expedition(
    ctrl: UIController,
    recognizer: UIRecognizer,
) -> tuple[UIController, list[int]]:
    """收取远征回报
    
    Returns: (操作后的 Controller, 收取的远征 ID 列表)
    """
    ctrl = navigate(recognizer, ctrl, "expedition_page")
    
    collected = []
    # ExpeditionPageController 有 detect_completed() 方法
    completed = ctrl.detect_completed()
    for exp_id in completed:
        ctrl.collect(exp_id)
        collected.append(exp_id)
        logger.info("收取远征 #{}", exp_id)
    
    return ctrl, collected


def dispatch_expedition(
    ctrl: UIController,
    recognizer: UIRecognizer,
    *,
    expedition_ids: list[int],
) -> UIController:
    """派遣远征"""
    ctrl = navigate(recognizer, ctrl, "expedition_page")
    
    for exp_id in expedition_ids:
        ctrl.select_expedition(exp_id)
        ctrl.dispatch()
        logger.info("派遣远征 #{}", exp_id)
    
    return ctrl
```

---

## 3. 解装操作

```python
# autowsgr/ops/destroy.py

from autowsgr.types import ShipType

def destroy_ships(
    ctrl: UIController,
    recognizer: UIRecognizer,
    *,
    ship_types: list[ShipType] | None = None,
    count: int = 10,
) -> UIController:
    """解装舰船
    
    Args:
        ship_types: 要解装的舰种。None = 全部可解装类型
        count: 解装数量
    """
    ctrl = navigate(recognizer, ctrl, "destroy_page")
    
    # DestroyPageController 封装了解装流程
    ctrl.add_ships(ship_types=ship_types, count=count)
    ctrl.confirm_destroy()
    
    logger.info("解装 {} 艘 (类型: {})", count, ship_types)
    return ctrl
```

---

## 4. 建造操作

```python
# autowsgr/ops/build.py

from dataclasses import dataclass

@dataclass
class BuildRecipe:
    """建造配方"""
    fuel: int
    ammo: int
    steel: int
    bauxite: int


def build_ship(
    ctrl: UIController,
    recognizer: UIRecognizer,
    *,
    recipe: BuildRecipe,
    slot: int = 0,  # 0=自动选择空闲槽位
) -> UIController:
    """建造舰船"""
    ctrl = navigate(recognizer, ctrl, "build_page")
    
    ctrl.select_slot(slot)
    ctrl.input_recipe(recipe.fuel, recipe.ammo, recipe.steel, recipe.bauxite)
    ctrl.confirm()
    
    logger.info("建造: {}/{}/{}/{}", recipe.fuel, recipe.ammo, recipe.steel, recipe.bauxite)
    return ctrl


def collect_built_ships(
    ctrl: UIController,
    recognizer: UIRecognizer,
) -> tuple[UIController, int]:
    """收取已建造完成的舰船
    
    Returns: (Controller, 收取数量)
    """
    ctrl = navigate(recognizer, ctrl, "build_page")
    count = ctrl.collect_completed()
    return ctrl, count
```

---

## 5. 做菜操作

```python
# autowsgr/ops/cook.py

def cook(
    ctrl: UIController,
    recognizer: UIRecognizer,
    *,
    position: int = 1,
) -> UIController:
    """在食堂做菜"""
    ctrl = navigate(recognizer, ctrl, "canteen_page")
    ctrl.cook_at(position)
    return ctrl
```

---

## 6. 日常任务编排

游戏操作层还提供高级的日常流程编排函数：

```python
# autowsgr/ops/daily.py

from dataclasses import dataclass
from autowsgr.infra.config import DailyConfig
from autowsgr.ui.recognizer import UIRecognizer
from autowsgr.ui.router import go_main_page


def run_daily_routine(
    recognizer: UIRecognizer,
    *,
    config: DailyConfig,
) -> None:
    """执行日常任务流程"""
    # 确保在主页
    ctrl = go_main_page(recognizer)
    
    # 1. 收远征
    ctrl, _ = collect_expedition(ctrl, recognizer)
    
    # 2. 收建造
    ctrl, _ = collect_built_ships(ctrl, recognizer)
    
    # 3. 收任务奖励
    ctrl = collect_rewards(ctrl, recognizer)
    
    # 4. 演习（如果配置开启）
    if config.exercise:
        ctrl = run_exercise(ctrl, recognizer, fleet_id=config.exercise_fleet_id)
    
    # 5. 战役（如果配置开启）
    if config.battle:
        ctrl = run_battle(ctrl, recognizer, fleet_id=config.battle_fleet_id)


def collect_rewards(
    ctrl: UIController,
    recognizer: UIRecognizer,
) -> UIController:
    """收取任务奖励"""
    ctrl = navigate(recognizer, ctrl, "mission_page")
    ctrl.collect_all_rewards()
    return navigate(recognizer, ctrl, "main_page")
```

---

## 函数式组合示例

```python
# 用户脚本示例

from autowsgr.infra.config import ConfigManager
from autowsgr.ops.sortie import prepare_sortie, SortieConfig
from autowsgr.ops.expedition import collect_expedition
from autowsgr.ui.router import go_main_page

# 初始化（由 bootstrap 完成）
recognizer = ...  

# 1. 回主页
ctrl = go_main_page(recognizer)

# 2. 收远征
ctrl, collected = collect_expedition(ctrl, recognizer)

# 3. 准备出击
ctrl = prepare_sortie(ctrl, recognizer, config=SortieConfig(
    chapter=5, map_id=4, fleet_id=1,
    fleet=["胡德", "俾斯麦", "", "", "", ""],
    repair_mode="medium",
))

# 4. 开始战斗（由战斗系统接管，见 07_combat_system.md）
from autowsgr.combat.engine import run_combat
result = run_combat(ctrl, recognizer, plan=my_plan)
```

---

## 与现有代码的映射

| 现有函数 (game_operation.py) | 新位置 | 变化 |
|---------------------------|--------|------|
| `get_ship(timer)` | 战斗系统内部 (`combat/`) | 战果结算的一部分 |
| `match_night(timer, is_night)` | 战斗系统内部 | 战斗决策的一部分 |
| `click_result(timer)` | 战斗系统内部 | 战果结算的一部分 |
| `destroy_ship(timer, types)` | `ops/destroy.py::destroy_ships()` | 函数式 |
| `verify_team(timer)` | `FightPrepareController.get_current_fleet_id()` | Controller 方法 |
| `move_team(timer, target)` | `FightPrepareController.switch_fleet()` | Controller 方法 |
| `quick_repair(timer, mode)` | `ops/sortie.py::apply_repair()` | 函数式策略 |
| `supply(timer, ids)` | `FightPrepareController.supply()` | Controller 方法 |
| `change_ship(timer, ...)` | `ops/sortie.py::change_fleet()` | 函数式 |
| `cook(timer, pos)` | `ops/cook.py::cook()` | 函数式 |
| `get_rewards(timer)` | `ops/daily.py::collect_rewards()` | 函数式 |
