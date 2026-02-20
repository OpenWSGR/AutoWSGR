# 游戏层重构 — 功能归属分类

## 分类原则

- **UIController**: 在**单个页面内**完成的原子操作（点击、检测状态、读取信息）
- **GameOps**: 涉及**跨页面导航**或**多个 UIController 协作**的组合操作
- **Combat**: 战斗过程中的操作（夜战、结算、敌方识别等），属于独立的战斗引擎

---

## 一、归属到 UIController（已有 / 需新增）

### 1. BattlePreparationPage（出征准备页）

| 旧函数 | 新方法 | 状态 | 说明 |
|--------|--------|------|------|
| `verify_team()` | `get_selected_fleet()` | ✅ 已有 | 像素检测选中队伍 |
| `move_team(target)` | `select_fleet(fleet)` | ✅ 已有 | 点击队伍标签 |
| `set_auto_supply(type)` | `toggle_auto_supply()` | ✅ 已有 | 点击复选框 |
| `set_support(target)` | `toggle_battle_support()` | ✅ 已有 | 点击支援开关 |
| `start_battle()` | `start_battle()` | ✅ 已有 | 点击开始出征 |
| `supply(ship_ids)` | `supply(ship_ids)` | ❌ 需新增 | 切换到补给面板 + 点击舰船位置 |
| `quick_repair(mode, ship_stats)` | `quick_repair(positions)` | ❌ 需新增 | 切换到修理面板 + 点击修理位置 |
| `detect_ship_stats()` | `detect_ship_damage()` | ❌ 需新增 | 像素检测6艘船血量状态 |
| `check_support_stats()` | `is_support_enabled()` | ❌ 需新增 | 像素检测支援状态 |

### 2. MapPage（地图页面）

| 旧函数 | 新方法 | 状态 | 说明 |
|--------|--------|------|------|
| `has_expedition_notification()` | 同名 | ✅ 已有 | 检测远征通知 |
| `get_active_panel()` | 同名 | ✅ 已有 | 当前面板 |
| `switch_panel()` | 同名 | ✅ 已有 | 切换面板 |
| `navigate_to_chapter()` | 同名 | ✅ 已有 | 章节导航 |

### 3. MainPage（主页面）

| 旧函数 | 新方法 | 状态 | 说明 |
|--------|--------|------|------|
| — | `has_expedition_ready()` | ❌ 需新增 | 主页面检测远征完成（像素检测） |

### 4. CanteenPage（食堂页面）

| 旧函数 | 新方法 | 状态 | 说明 |
|--------|--------|------|------|
| `cook(position)` 中的点击操作 | `select_recipe(position)` | ❌ 需新增 | 点击菜谱位置 |

### 5. BuildPage（建造页面）

已有标签切换。具体建造槽位操作暂缓（建造逻辑较复杂，后续拆分）。

---

## 二、归属到 GameOps（跨页面组合操作）

### 1. `ops/navigate.py` — 跨页面导航

| 函数 | 说明 |
|------|------|
| `goto_page(ctrl, target_page)` | 从任意页面导航到目标页面（利用导航图 BFS） |
| `go_main_page(ctrl)` | 从任意页面回到主页面（兜底导航） |

### 2. `ops/sortie.py` — 出征准备

| 旧函数 | 新函数 | 说明 |
|--------|--------|------|
| `change_ship()` + `change_ships()` | `change_fleet(ctrl, fleet, ship_names)` | 换船：准备页 → 选船页 → 准备页，涉及多页面 |
| `quick_repair()` (策略判断部分) | `apply_repair(ctrl, mode)` | 读取血量 + 按策略决定修理位置 + 调用 UI 修理 |

### 3. `ops/expedition.py` — 远征

| 旧函数 | 新函数 | 说明 |
|--------|--------|------|
| `Expedition.run()` | `collect_expedition(ctrl)` | 导航到远征页 → 收取 → 重新派遣 |

### 4. `ops/destroy.py` — 解装

| 旧函数 | 新函数 | 说明 |
|--------|--------|------|
| `destroy_ship()` | `destroy_ships(ctrl, ship_types)` | 主页 → 解装页 → 选择 → 执行 → 回主页 |

### 5. `ops/build.py` — 建造

| 旧函数 | 新函数 | 说明 |
|--------|--------|------|
| `BuildManager.build()` | `build_ship(ctrl, recipe)` | 导航到建造页 → 输入资源 → 确认 |
| `BuildManager.get_build()` | `collect_built_ships(ctrl)` | 导航到建造页 → 收取 |

### 6. `ops/cook.py` — 做菜

| 旧函数 | 新函数 | 说明 |
|--------|--------|------|
| `cook(timer, pos)` | `cook(ctrl, position)` | 导航到食堂 → 选菜谱 → 做菜 |

### 7. `ops/reward.py` — 任务奖励

| 旧函数 | 新函数 | 说明 |
|--------|--------|------|
| `get_rewards()` | `collect_rewards(ctrl)` | 主页 → 任务页 → 领取 → 回主页 |

### 8. `ops/repair.py` — 浴室修理

| 旧函数 | 新函数 | 说明 |
|--------|--------|------|
| `repair_by_bath()` | `repair_in_bath(ctrl)` | 导航到浴室 → 选择修理 → 执行 |

---

## 三、归属到战斗系统（Combat）— 本次不实现

| 旧函数 | 归属 | 说明 |
|--------|------|------|
| `get_ship()` | `combat/` | 战果结算时识别掉落 |
| `match_night()` | `combat/` | 夜战界面点击 |
| `click_result()` | `combat/` | 战果跳过 |
| `get_enemy_condition()` | `combat/` | 索敌后识别敌方舰船 |
| `get_enemy_formation()` | `combat/` | 识别敌方阵型 |
| `detect_ship_stats(type='sumup')` | `combat/` | 战后血量检测 |
| `get_exercise_stats()` | `combat/` 或 `ops/exercise.py` | 演习状态 |

---

## 四、实现计划

### Phase 1: 补全 UIController 方法

1. `BattlePreparationPage` 新增: `supply()`, `quick_repair()`, `detect_ship_damage()`, `is_support_enabled()`
2. `MainPage` 新增: `has_expedition_ready()`
3. `CanteenPage` 新增: `select_recipe()`

### Phase 2: 实现 GameOps 层

1. `ops/navigate.py` — goto_page / go_main_page
2. `ops/sortie.py` — change_fleet / apply_repair
3. `ops/reward.py` — collect_rewards
4. `ops/cook.py` — cook
5. `ops/destroy.py` — destroy_ships
6. `ops/expedition.py` — collect_expedition
7. `ops/build.py` — build_ship / collect_built_ships
8. `ops/repair.py` — repair_in_bath

### 设计模式

所有 GameOps 函数遵循统一模式:

```python
def some_operation(
    ctrl: AndroidController,
    *,
    param1: ...,
) -> SomeResult:
    """
    1. 利用 goto_page 导航到目标页面
    2. 构造页面 Controller 执行原子操作
    3. 返回结果
    """
```

- 无状态函数，不维护 `now_page`
- 依赖 `get_current_page()` 识别当前页面
- 利用导航图 `find_path()` 规划路径
- 每一步导航使用 `click_and_wait_for_page()` 验证
