# 后端死代码分析

## 1. 分析范围

- 分支：`ShiinaKuroko`
- 基线提交：`3195808`
- 扫描范围：`autowsgr/`、`testing/`、`examples/`、`tools/` 和 `docs/`
- 目标：区分可安全删除的内部残留、必须保留的兼容接口，以及不能仅凭静态引用判断的公开 API

工作区中的 scrcpy 实验改动、基准图片和未提交 OCR 文档不在本次分析范围内。

## 2. 分析方法

本次分析同时使用以下证据，避免直接采用静态扫描结果：

1. Ruff 检查未使用导入、重复定义和未使用局部变量。
2. Vulture 扫描无引用的函数、方法、属性、类和常量。
3. `git grep` 核对生产代码、测试、示例和文档中的真实引用。
4. 检查各包的 `__all__`，确认对象是否属于公开 API。
5. 查看 `git log -S` 和历史版本，判断对象是否承担迁移或兼容职责。
6. 对同名模块与子包执行 Python 导入解析，确认实际加载目标。

Ruff 未发现未使用导入或局部变量。Vulture 的原始结果包含 FastAPI 路由、
Pydantic 校验器、协议方法、动态处理器和资源生命周期引用等误报，均经过人工复核。

## 3. 本次删除

删除 `autowsgr/ui/battle/fleet_change.py`。

该文件是拆分前的旧版 `FleetChangeMixin`，当前同时存在同名子包：

```text
autowsgr/ui/battle/fleet_change.py
autowsgr/ui/battle/fleet_change/
```

Python 对 `autowsgr.ui.battle.fleet_change` 的解析结果始终是
`fleet_change/__init__.py`。仓库中的导入也全部指向该子包或其内部模块，因此旧文件
无法被正常导入和执行。

删除该文件不会改变以下公开导入：

```python
from autowsgr.ui.battle.fleet_change import FleetChangeMixin
```

删除后还可消除文件与包同名造成的维护歧义，避免后续修改落到实际不会执行的文件。

## 4. 后续可安全删除的内部残留

以下对象未导出、无生产调用、无测试引用，也没有兼容说明：

| 模块 | 可删除对象 |
| --- | --- |
| `combat/actions.py` | `FLAGSHIP_CONFIRM` |
| `ui/decisive/overlay.py` | `CLICK_BUY_EXP`、`CLICK_SKILL`、`is_advance_choice`、`is_confirm_exit` |
| `ui/main_page/constants.py` | `EVENT_SIDEBAR_BG` |
| `ui/map/data.py` | `EXPEDITION_IDLE_COLOR`、`SIDEBAR_SCAN_*`、`RIVAL_POSITIONS`、`CLICK_CHALLENGE` |
| `ui/tabbed_page.py` | `TAB_DARK` |
| `server/schemas.py` | `SystemStatusResponse`、`LogMessage`，以及随之失去引用的 `LogLevel` |
| `server/ws_manager.py` | `send_log`，以及仅由它使用的 `UTC`、`datetime` 导入 |

本次精简批次已删除前表中已移除的私有死代码：`click_start_march`、
`_SHIP_TYPE_DISPLAY_MAP`、`_SHIP_TYPE_PATTERN`、`self._destroy_ship_types` 赋值、
两个未使用的启动常量、scrcpy 滚动消息常量、浴室时间常量、舰队 OCR 名称预处理
helper、舰船列表中心点 helper、等级标签正则，以及 `LazyTemplate` 未读取的属性赋值。
删除前均通过全仓引用扫描确认无调用。剩余项目继续按模块分批删除，并执行对应聚焦测试。

## 5. 必须保留的兼容接口

以下对象虽然仓库内调用较少或没有调用，但承担明确兼容职责：

| 接口 | 保留原因 |
| --- | --- |
| `RESULT_GRADE_TEMPLATES` | 源码明确标注为向后兼容别名 |
| `MainPageTarget`、`OverlayType` | `autowsgr.ui` 对旧名称提供的兼容别名 |
| `navigate_to_event(..., is_base_page=...)` | 保留旧调用签名，参数当前不参与实现 |
| `migrate_raw_config`、`migrate_plan_dict` | 旧设置和旧计划迁移入口 |
| `Templates.Fight.result_pages()` | 从旧 `ops.image_resources` 保留下来的资源接口 |

不能仅因为仓库内没有直接调用就删除这些接口。若未来需要移除，应先增加弃用告警，
经过至少一个兼容周期后再进行破坏性变更。

## 6. 公开 API，不按死代码处理

以下对象所属类已通过包级 `__all__` 导出，外部脚本可能直接调用：

- `CombatEngine.set_node`
- `FleetSlotRule.preferred_name`
- `NodeTracker.ship_position`
- `Fleet.damage_states`、`Ship.health_ratio`
- `Color.from_bgr`
- `BuildPage`、`MainPage`、`MissionPage` 和 `DecisiveMapController` 的公开方法
- Campaign、Exercise 等 `MapPage` Mixin 的公开方法
- `NetworkError`、`CombatDecisionError`、`SearchEnemyAction`

静态扫描无法观察仓库外调用，删除这些对象需要先确认公开 API 策略，而不能作为普通
内部死代码直接处理。

## 7. 需要单独决策的接口

### `FightRunnerProtocol`

该协议当前没有参与运行时判断和类型标注，但架构文档明确把它描述为 Runner 公共协议。
建议保留并用于 `FightTask.runner` 的类型定义，或者先从文档和公开入口中弃用后再删除。

### `make_page_checker`

该函数最初设计为页面注册工厂，但当前没有调用，也未通过 `autowsgr.ui` 导出。若确认
不存在外部直接导入，可以删除；更保守的做法是先标记弃用。

### `recognize_rival_formation`

该方法目前只截图并返回 `None`，属于未实现的预留接口，并非已工作的兼容功能。近期
没有实现计划时应删除，避免调用方误认为它可以返回有效阵容。

## 8. 静态扫描误报

以下模式不能按死代码删除：

- FastAPI 的 `@router.*` 和 `@app.websocket` 装饰器注册函数。
- Pydantic 的 `@field_validator`、`@model_validator` 及模型字段。
- 状态机通过映射或动态分派调用的 `_handle_*` 方法。
- Protocol 中由实现类调用的方法签名。
- Lazy descriptor 的 `obj`、`objtype` 参数。
- 用于维持底层对象生命周期的 `_resource`、`_resource_holder` 属性。
- 枚举成员和序列化模型字段。

## 9. 清理原则

1. 优先删除私有、未导出、无引用且无兼容说明的对象。
2. 公开 API 和兼容别名必须经过弃用周期。
3. 每批清理只覆盖一个模块边界，并运行对应聚焦测试。
4. 删除后运行 Ruff、pytest 和 `git diff --check`，避免产生级联未使用导入。
