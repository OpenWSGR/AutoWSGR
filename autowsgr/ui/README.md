## 测试计划

## 功能简介

UI 控制层提供单个游戏界面的建模和抽象，封装页面识别、状态查询和操作动作。

- **页面识别** — 每个页面均提供 `is_current_page(screen)` 静态方法。
- **状态查询** — `staticmethod`，只需截图数组。
- **操作动作** — 实例方法，通过注入的 `GameContext` 执行。

---

### MainPage

```python
class MainPage:
    # 状态查询
    @staticmethod
    def is_current_page(screen) -> bool: ...
    @staticmethod
    def is_base_page(screen) -> bool:
        """判断是否为主页面基础状态 (不含浮层)。"""
    @staticmethod
    def detect_overlay(screen) -> OverlayKind | None:
        """检测当前浮层类型 (新闻/签到/预约)。"""
    @staticmethod
    def has_expedition_ready(screen) -> bool:
        """检测是否有远征完成可收取。"""
    @staticmethod
    def has_task_ready(screen) -> bool:
        """检测是否有任务奖励可领取。"""

    # 操作
    def dismiss_current_overlay(self) -> bool:
        """检测并消除当前浮层，返回 True 表示已处理。"""
    def navigate_to(self, target: Target) -> None:
        """导航到子页面 (出征/任务/侧边栏/后院/活动)，自动处理浮层。"""
    def go_to_sortie(self) -> None: ...
    def go_to_task(self) -> None: ...
    def open_sidebar(self) -> None: ...
    def go_home(self) -> None: ...
    def go_to_event(self) -> None: ...
```

---

### MapPage

通过 Mixin 组合出征 / 战役 / 演习 / 远征 / 决战五个面板的完整能力。

```python
class MapPage(SortiePanelMixin, CampaignPanelMixin, DecisivePanelMixin,
              ExercisePanelMixin, ExpeditionPanelMixin):
    # 页面识别与状态
    @staticmethod
    def is_current_page(screen) -> bool: ...
    @staticmethod
    def get_active_panel(screen) -> MapPanel | None:
        """获取当前激活的面板标签。"""
    @staticmethod
    def has_expedition_notification(screen) -> bool:
        """检测是否有远征完成通知。"""
    @staticmethod
    def recognize_map(screen, ocr) -> MapIdentity | None:
        """通过 OCR 识别当前地图 (章节号 + 地图号)。"""

    # 导航与面板
    def switch_panel(self, panel: MapPanel) -> None:
        """切换面板 (出征/演习/远征/战役/决战)。"""
    def ensure_panel(self, panel: MapPanel) -> None:
        """确保处于指定面板，若不是则自动切换。"""
    def navigate_to_chapter(self, target: int) -> int | None:
        """通过 OCR 导航到指定章节 (1–9)。"""
    def go_back(self) -> None:
        """返回主页面。"""

    # 出征面板
    def enter_sortie(self, chapter: int | str, map_num: int | str) -> None:
        """选择章节和地图，进入出征准备页面。"""

    # 战役面板
    def recognize_difficulty(self) -> str | None:
        """识别当前战役难度 ("easy" / "hard")。"""
    def enter_campaign(self, map_index: int, difficulty: str, campaign_name: str) -> None:
        """选择难度和战役类型，进入出征准备页面。"""
    def get_acquisition_counts(self) -> AcquisitionCounts:
        """OCR 识别今日舰船 (X/500) 与战利品 (X/50) 获取数量。"""

    # 演习面板
    def get_exercise_rival_status(self) -> ExerciseRivalStatus:
        """检测 5 个演习对手的可挑战状态。"""
    def select_exercise_rival(self, rival_index: int) -> None:
        """点击选择指定对手 (1–5)。"""
    def enter_exercise_battle(self) -> None:
        """在对手信息页开始战斗，进入出征准备页面。"""
    def challenge_rival(self, rival_index: int) -> None:
        """选择对手并直接进入出征准备 (组合快捷方法)。"""

    # 远征面板
    @staticmethod
    def find_ready_expedition_slot(screen) -> int | None:
        """检测第一个已完成远征的槽位 (0–3)。"""
    def collect_expedition(self) -> int:
        """收取所有已完成远征，返回收取数量。"""

    # 决战面板
    def enter_decisive(self) -> None:
        """进入决战总览页。"""
```

---

### BattlePreparationPage

通过 Mixin 组合检测 / 补给支援 / 修理 / 换船四大能力。

```python
class BattlePreparationPage(DetectionMixin, SupplyMixin, RepairMixin,
                            FleetChangeMixin, BaseBattlePreparation):
    # ── 页面识别与基础状态 ──
    @staticmethod
    def is_current_page(screen) -> bool: ...
    @staticmethod
    def get_selected_fleet(screen) -> int | None:
        """获取当前选中的舰队编号 (1–4)。"""
    @staticmethod
    def get_active_panel(screen) -> Panel | None:
        """获取当前激活的底部面板 (综合战力/快速补给/快速修理/装备预览)。"""
    @staticmethod
    def is_auto_supply_enabled(screen) -> bool:
        """检测自动补给是否启用。"""

    # ── 导航 ──
    def go_back(self) -> None:
        """返回地图页面。"""
    def start_battle(self) -> None:
        """点击「开始出征」。"""
    def select_fleet(self, fleet: int) -> None:
        """选择舰队 (1–4)。"""
    def select_panel(self, panel: Panel) -> None:
        """切换底部面板标签。"""

    # ── 检测 (DetectionMixin) ──
    @staticmethod
    def detect_ship_damage(screen) -> dict[int, ShipDamageState]:
        """检测 6 个槽位的血量状态 (正常/中破/大破/无舰船)。"""
    def detect_fleet_info(self, fleet_id: int | None = None) -> FleetInfo:
        """识别指定舰队详细信息 (等级 + 血量)。
        fleet_id 为 None 则不切换，直接识别当前舰队。"""

    # ── 补给与支援 (SupplyMixin) ──
    @staticmethod
    def is_support_enabled(screen) -> bool:
        """检测战役支援是否启用 (含次数用尽)。"""
    def toggle_battle_support(self) -> None:
        """切换战役支援开关。"""
    def supply(self, ship_ids: list[int] | None = None) -> None:
        """切换到补给面板并补给指定舰船 (默认全部)。"""
    def apply_supply(self) -> None:
        """确保舰队已补给 (自动补给未开则手动补给)。"""

    # ── 修理 (RepairMixin) ──
    def repair_slots(self, positions: list[int]) -> None:
        """切换到快速修理面板并修理指定位置。"""
    def apply_repair(self, strategy: RepairStrategy = SEVERE) -> list[int]:
        """按策略自动修理，返回实际修理的槽位列表。"""

    # ── 换船 (FleetChangeMixin) ──
    def change_fleet(self, fleet_id: int | None, ship_names: Sequence[str | None]) -> bool:
        """更换编队全部舰船 (fleet_id=1 不支持)。"""
```

**FleetInfo** 数据类:

```python
@dataclass
class FleetInfo:
    fleet_id: int | None       # 舰队编号
    ship_levels: dict[int, int | None]  # 槽位 → 等级
    ship_damage: dict[int, ShipDamageState]  # 槽位 → 血量状态
```

**AcquisitionCounts** 数据类:

```python
@dataclass
class AcquisitionCounts:
    ship_count: int | None   # 今日已获取舰船
    ship_max: int | None     # 舰船上限 (如 500)
    loot_count: int | None   # 今日已获取战利品
    loot_max: int | None     # 战利品上限 (如 50)
```

---

### BackyardPage

```python
class BackyardPage:
    @staticmethod
    def is_current_page(screen) -> bool: ...

    def go_to_bath(self) -> None:
        """进入浴室。"""
    def go_to_canteen(self) -> None:
        """进入食堂。"""
    def go_back(self) -> None:
        """返回主页面。"""
```

---

### BathPage

```python
class BathPage:
    @staticmethod
    def is_current_page(screen) -> bool:
        """含 overlay 状态均识别为浴室。"""
    @staticmethod
    def has_choose_repair_overlay(screen) -> bool:
        """判断选择修理浮层是否打开。"""

    def go_to_choose_repair(self) -> None:
        """打开选择修理浮层。"""
    def close_choose_repair_overlay(self) -> None:
        """关闭选择修理浮层。"""
    def click_first_repair_ship(self) -> None:
        """点击第一个需修理舰船 (自动关闭 overlay)。"""
    def go_back(self) -> None:
        """overlay 打开时关闭 overlay，否则返回上一页。"""
```

---

### BuildPage

```python
class BuildPage:
    @staticmethod
    def is_current_page(screen) -> bool: ...
    @staticmethod
    def get_active_tab(screen) -> BuildTab | None:
        """获取当前标签 (建造/解体/开发/废弃)。"""

    def switch_tab(self, tab: BuildTab) -> None:
        """切换标签。"""
    def collect_all(self, build_type="ship", *, allow_fast_build=False) -> int:
        """收取已完成的舰船或装备，返回数量。"""
    def start_new_build(self, build_type="ship") -> None:
        """启动一次新建造。"""
    def destroy_ships(self, ship_types=None, *, remove_equipment=True) -> None:
        """执行完整解装流程。"""
    def go_back(self) -> None:
        """返回侧边栏。"""
```

---

### CanteenPage

```python
class CanteenPage:
    @staticmethod
    def is_current_page(screen) -> bool: ...

    def cook(self, position: int = 1, *, force_cook: bool = False) -> bool:
        """选择菜谱并做菜。force_cook=True 时覆盖正在生效的菜。"""
    def go_back(self) -> None:
        """返回后院。"""
```

---

### ChooseShipPage

```python
class ChooseShipPage:
    def click_search_box(self) -> None:
        """点击搜索框。"""
    def input_ship_name(self, name: str) -> None:
        """输入舰船名。"""
    def dismiss_keyboard(self) -> None:
        """关闭软键盘。"""
    def click_first_result(self) -> None:
        """点击搜索结果第一项。"""
    def click_remove(self) -> None:
        """移除当前槽位舰船。"""
```

---

### SidebarPage

```python
class SidebarPage:
    @staticmethod
    def is_current_page(screen) -> bool: ...

    def navigate_to(self, target: SidebarTarget) -> None:
        """进入子页面 (建造/强化/好友)，建造和强化含二级菜单。"""
    def close(self) -> None:
        """关闭侧边栏。"""
```

---

### IntensifyPage

```python
class IntensifyPage:
    @staticmethod
    def is_current_page(screen) -> bool: ...
    @staticmethod
    def get_active_tab(screen) -> IntensifyTab | None: ...

    def switch_tab(self, tab: IntensifyTab) -> None:
        """切换标签 (强化/改修/技能)。"""
    def go_back(self) -> None:
        """返回侧边栏。"""
```

---

### FriendPage

```python
class FriendPage:
    @staticmethod
    def is_current_page(screen) -> bool: ...

    def go_back(self) -> None:
        """返回侧边栏。"""
```

---

### MissionPage

```python
class MissionPage:
    @staticmethod
    def is_current_page(screen) -> bool: ...

    def collect_rewards(self) -> bool:
        """收取任务奖励 (尝试一键领取 → 单个领取)，返回是否成功。"""
    def go_back(self) -> None:
        """返回主页面。"""
```

---

### StartScreenPage

```python
class StartScreenPage:
    @staticmethod
    def is_current_page(screen) -> bool: ...

    def click_enter(self) -> None:
        """点击「点击进入」按钮，进入游戏主流程。"""
```

---

## 未来计划
