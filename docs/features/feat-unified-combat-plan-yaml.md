# Feat: 统一 GUI 与后端作战计划 YAML 契约

## 状态

- 日期：2026-08-01
- 阶段：后端解析已收口，GUI 改造待办
- 实现状态：暂停，择日继续 GUI 部分
- 当前结论：`combat/plan.py` 只做列表类型校验和基础整理，严格格式约束留给 GUI
  与后续共享 Schema。

## 背景

当前存在三套并不完全一致的作战计划入参：

1. AutoWSGR-GUI 保存和编辑的 YAML。
2. AutoWSGR 的 `CombatPlan.from_yaml()`。
3. AutoWSGR HTTP API 的 `CombatPlanRequest`。

GUI 当前允许在舰队槽位中使用 `nation` 和 `priority`，并在发送 API 前将其转换为
`candidates`。旧后端对节点和部分枚举有校验，但对 `fleet` 没有正式约束。

## 目标

1. GUI 保存的 YAML 与后端直接读取的 YAML 使用同一份字段定义。
2. 明确定义 YAML 到 HTTP API 运行时字段的转换，不允许“接口接受但执行时忽略”。
3. 已经在 GUI 或后端实际使用的字段保持原语义，只定义缺失的字段和转换规则。
4. 提供一份可供 Python 和 TypeScript 共用的 Schema。
5. 不经过 GUI 的后端 YAML 路径也必须得到与 GUI 相同的解析结果。

## 建议的统一方向

统一契约需要明确区分两层字段：

1. YAML 编排字段：保留 GUI 已使用的 `name`、`nation`、`ship_type`、`priority`、
   `min_level`、`max_level`。
2. 后端运行时字段：`candidates`、`search_name`、`ship_type`、`min_level`、`max_level`。

GUI 已经使用 `nation` 筛选船池、使用 `priority` 排候选顺序，所以不能删除或改名。
需要补充的是统一的“编排字段转运行时字段”规则。后端若要直接读取同一份 YAML，也必须执行
等价转换；不能只在 GUI 中转换。

该方向尚未实现，最终字段需要在 GUI 和后端共同修改时确认。

## 当前改动概述

当前分支的 `autowsgr/combat/plan.py` 已增加：

- `fleet_presets` 解析。
- 只校验 `fleet_presets` 是否为列表，空列表表示不使用舰队预设。
- 去除预设名称、舰名和槽位字符串字段的首尾空格。
- `candidates` 去重。
- 将每个 preset 整理为统一的 `name + ships` 结构。

后端原先新增的字段白名单、非空、六槽、等级范围和未知字段校验已删除。完整格式约束尚未
同步 GUI 和 HTTP API，因此仍不是本 feat 的最终方案。

## 上游活动 YAML 改动影响（#516）

### 结论

上游活动改动与 `fleet_presets` 没有直接冲突。两组改动都位于
`CombatPlan.from_dict()`，但分别处理顶层地图字段和舰队字段，可以自动合并并同时保留。

该改动会影响统一 YAML Schema 对顶层字段的定义，因此后续不能再把 `chapter` 和 `map`
限制为整数，也不能继续使用独立的 `map_entrance` 字段。

### 上游确定的新语义

- 普通地图继续使用数字 `chapter` 和数字 `map`。
- 活动地图使用 `chapter: E` 表示简单难度，使用 `chapter: H` 表示困难难度。
- 活动入口写入 `map`：`1a` 表示第 1 图 α 入口，`1b` 表示第 1 图 β 入口。
- `CombatPlan.from_dict()` 将 `map: 1a` 整理为 `map_id=1` 和内部字段
  `entrance='a'`；`entrance` 不是独立的 YAML 字段。
- `map` 只接受数字、数字字符串或“数字 + a/b”；其他内容会抛出 `ValueError`。
- `event` 保存活动目录名，例如 `"20260730"`，运行时进入 `CombatPlan.event_name`。
- 原配置字段 `map_entrance` 已从后端配置模型删除，不应进入新的共享 Schema。
- `NormalFightRunner` 根据 `chapter` 是否为 `E/H` 决定活动或普通战，并修正运行时
  `mode`；因此 `mode` 不再是这两类出击的唯一分流依据。

### 对 GUI 和 HTTP API 的影响

当前 AutoWSGR-GUI 尚不能无损读取这种活动 YAML：

- `PlanData.chapter` 和 `PlanData.map` 仍定义为 `number`。
- `PlanModel.fromYaml()` 对两个字段调用 `Number()`，会把 `H` 和 `1a` 都转换为 `0`。
- `PlanData` 没有 `event` 字段，重新保存时会丢失活动名称。

HTTP API 虽然允许 `chapter` 和 `map` 为字符串，但 serializer 仍直接执行
`map_id=request.map`，没有调用 `parse_map_value()`，也没有复制 `event_name`。因此直接通过
API 传入 `chapter: H`、`map: 1a` 时，会得到错误的 `map_id='1a'`、空入口和空活动名称。

统一契约后续需要规定：

1. `chapter` 为普通章节数字，或活动难度 `E/H`。
2. `map` 为正整数，或匹配 `^\d+[aAbB]?$` 的字符串。
3. 当 `chapter` 为 `E/H` 时允许入口后缀，并要求活动名称字段。
4. YAML 的 `event`、API 的 `event_name` 和运行时 `CombatPlan.event_name` 必须有明确转换。
5. GUI 与 API 必须复用后端 `parse_map_value()` 的等价规则，不能各自转换。

## TODO：AutoWSGR-GUI

- GUI 加载 YAML 时，将 `nation`、`priority` 等编排字段转换为标准 `candidates`。
- GUI 内部、保存 YAML 和发送 API 使用同一份标准舰队结构。
- 将 `chapter`、`map` 扩展为活动格式，并保证 `H`、`E`、`1a`、`1b` 无损往返。
- 增加并保留 YAML 顶层 `event` 字段，不在 GUI 保存时丢失。
- 更新 GUI 的类型定义、舰队编辑器和内置 YAML。
- 增加 GUI 加载、保存和 API 入参的契约测试。
- GUI 改造完成后，再确定共享 Schema 和后端最终校验方式。

## 后端字段功能审计

### CombatPlan 顶层字段

| YAML 字段 | 状态 | 实际行为 |
| --- | --- | --- |
| `name` | 部分有效 | 仅用于日志和任务名称，不改变作战行为。 |
| `mode` | 部分有效 | 决定状态转移图；普通/活动 Runner 会再按 `chapter` 是否为 `E/H` 修正为 `normal/event`。 |
| `chapter` | 有效 | 普通战使用章节数字；活动使用 `E/H`，并据此选择普通或活动导航。 |
| `map` | 有效且已约束 | 接受数字、数字字符串或 `1a/1b` 格式；后缀表示活动入口，非法格式抛出 `ValueError`。 |
| `fleet_id` | 有效 | 用于选择出征舰队。 |
| `fleet` | 有效 | 旧格式固定舰名列表，准备页会执行换船；旧后端没有格式校验。 |
| `fleet_presets` | 当前分支部分有效 | 后端只解析和保存，不在作战入口轮询多个 preset；实际出击一次只执行一套舰队。 |
| `repair_mode` | 部分有效 | 会触发快速修理，但六槽配置被取最小值后作为全队修理策略，未逐槽执行。 |
| `fight_condition` | 有效 | 在战况选择页面点击对应选项。 |
| `selected_nodes` | 有效 | 作为节点白名单，不在列表中的节点会撤退或 SL。 |
| `node_defaults` | 有效 | 构造默认节点决策。 |
| `node_args` | 有效 | 覆盖指定节点的决策。 |
| `event` | 有效 | 活动目录名，解析后保存到 `CombatPlan.event_name`，用于加载活动地图节点数据。 |
| `map_entrance` | 已删除 | 入口已编码进 `map` 的 `a/b` 后缀，不应再写入 YAML 或共享 Schema。 |
| `entrance` | 非 YAML 字段 | 由 `map` 解析得到的内部字段，不应要求用户重复配置。 |
| `nodes` | 无效的 YAML 名称 | 架构文档示例写成了 `nodes`，实际解析器只读取 `node_args`。 |
| `endpoint_nodes` | GUI 有效 | 后端不读取；GUI 调度器用它判断本轮到达哪个节点后计为完成。 |

`testing/plan` 中的 `times`、`gap`、`stop_condition`、`loot_count_ge` 属于测试或调度层元数据，
不由 `CombatPlan.from_yaml()` 解析。

### 舰队 preset 和槽位字段

| 字段 | 状态 | 实际行为 |
| --- | --- | --- |
| preset `name` | GUI 有效、后端仅保存 | GUI 用它展示和选择 preset；后端当前不使用它选择出击舰队。 |
| preset `ships` | 有效 | 作为该 preset 唯一的舰队槽位列表。 |
| slot `name` | 有效 | 作为该槽位的主选舰名。 |
| slot `candidates` | 有效 | 按顺序尝试候选，并参与槽位级唯一分配。 |
| slot `search_name` | 有效 | 用于搜索框关键字和自定义舰名区分。 |
| slot `min_level` | 部分有效 | 重新选船时 OCR 读取等级并过滤；当前槽已有同名舰时不会复核等级。 |
| slot `max_level` | 部分有效 | 与 `min_level` 相同，仅在重新选船时过滤。 |
| slot `ship_type` | 部分有效 | 重新选船时 OCR 识别舰种并过滤；当前槽已有同名舰时不会复核舰种。 |
| `priority` | GUI 有效 | GUI 用它调整候选顺序并转换为 `candidates`；后端当前不直接处理。 |
| `nation` | GUI 有效 | GUI 用它筛选船池并生成 `candidates`；后端当前没有国籍筛选能力。 |

`ship_type` 当前运行时支持：

`dd`、`cl`、`ca`、`cav`、`clt`、`bb`、`bc`、`bbv`、`cv`、`cvl`、`av`、`ss`、
`ssg`、`cg`、`cgaa`、`ddg`、`ddgaa`、`bm`、`cbg`、`cf`，以及组合规则
`ss_or_ssg`。

GUI 舰船数据还使用 `bbg` 表示导战，但当前后端 API 白名单和选船页舰种 OCR 表都不支持
`bbg`。

### GUI 字段审计修正

判断字段是否有效必须同时检查 GUI 和后端：

- `endpoint_nodes`：GUI 调度器用于判断一轮任务的完成节点。
- preset `name`：GUI 用于显示和选择队伍预设。
- `nation`：GUI 使用舰船数据库按国籍生成候选。
- `priority`：GUI 用于排序候选。
- `times`、`gap`、`stop_condition`、`loot_count_ge`：由 GUI 调度或任务层使用，不属于
  `CombatPlan` 战斗执行字段。

这些字段不能因为后端 `CombatPlan` 没有读取就删除。

### 密苏里舰种最小验证

GUI 舰船数据中存在：

- `密苏里`：美国，`bb`，战列。
- `密苏里·改`：美国，`bbg`，导战。

当前后端最小验证结果：

```text
密苏里 / 战列 / bb: OCR='bb', match=True, API=accepted
密苏里·改 / 导战 / bbg: OCR=None, match=False, API=rejected
```

结论：战列型可以按 `ship_type=bb` 识别；导战型当前不能按 `ship_type=bbg` 识别。

### 突击者舰种实机验证

GUI 舰船数据中存在：

- `突击者`：美国，`cvl`，轻母。
- `突击者·改`：美国，`cv`，航母。

在 720P、240 DPI 的实机选船页中，对同一个槽位直接执行两次替换：

```text
航母/cv: selected='突击者', detected_types=['cv']
轻母/cvl: selected='突击者', detected_types=[None, 'cvl']
```

测试通过。第二次选择中，第一次未识别出舰种时没有点击，识别出 `cvl` 后才选择，证明
`ship_type` 在实际重新选船路径中生效。

该结果不代表现有编队验证完整：如果当前槽已经识别为同名 `突击者`，`change_fleet()`
仍可能只比较舰名并提前短路，不会重新验证 `cv/cvl`。

### 国籍筛选审计

当前后端战斗选船系统没有国籍筛选功能：

- `FleetRuleRequest` 没有 `nation` 字段。
- `ChooseShipPage` 没有国籍 OCR 或国籍筛选参数。
- 后端舰名库没有可供选船逻辑使用的“舰名到国籍”映射。

国籍筛选目前完全在 GUI 的 `shipData.ts` 中完成，GUI 将筛选结果转换成 `candidates`
后再传给后端。

### NodeDecision 字段

以下字段在 YAML 路径中都有实际执行代码：

- `formation`
- `night`
- `proceed`
- `proceed_stop`
- `enemy_rules`
- `enemy_formation_rules`
- `detour`
- `long_missile_support`
- `SL_when_spot_enemy_fails`
- `SL_when_detour_fails`
- `SL_when_enter_fight`
- `formation_when_spot_enemy_fails`

注意：`NodeDecision` 内部属性叫 `formation_rules`，但 YAML 正式入参叫
`enemy_formation_rules`。在 YAML 中写 `formation_rules` 会被 Pydantic 默认忽略。

### 枚举

| 枚举 | 有效值 | 状态 |
| --- | --- | --- |
| `mode` | `normal`、`battle`、`exercise`、`decisive`、`event` | 实际控制战斗状态机。 |
| `fight_condition` | `1` 至 `5` | 实际控制战况点击。 |
| `formation` | `1` 至 `5` | 实际控制阵型点击。 |
| `repair_mode` | `1` 中破修、`2` 大破修、`3` 不触发快速修理 | 有效，但列表未逐槽执行。 |
| `proceed_stop` | `1` 中破停止、`2` 大破停止、`3` 不因当前血量停止 | 支持逐槽判断；当前血量枚举最高为 `2`，所以阈值 `3` 实际不会触发停止。 |

## HTTP API 审计结果

API 与 YAML 目前也不一致：

- `NodeDecisionRequest.enemy_rules` 会被 API 接受，但 `build_combat_plan()` 没有复制到
  `NodeDecision`，因此通过直接 API plan 传入时不生效。
- YAML 支持的 `enemy_formation_rules`、导弹支援和三个 SL 字段没有出现在
  `NodeDecisionRequest` 中。
- `CombatPlanRequest.event_name` 会被 API 接受，但 `build_combat_plan()` 没有写入
  `CombatPlan.event_name`。
- `CombatPlanRequest.map` 接受 `1a/1b` 字符串，但 `build_combat_plan()` 没有调用
  `parse_map_value()`；直接 API 路径不会拆出 `map_id` 和 `entrance`。
- API 的 `fight_condition` 是整数，serializer 没有转换成 `FightCondition`，而执行器会访问
  `.value`，直接 API plan 路径存在类型错误风险。
- `fleet_rules` 会由 task route 单独传给 Runner，因此实际生效，但没有进入
  `CombatPlan`，与 YAML 路径不是同一模型。

## 进度

- [x] 确认 GUI YAML 的舰队字段和转换位置。
- [x] 确认 main 后端原有 YAML 约束范围。
- [x] 审计 `combat-engine.md` 中的 CombatPlan 和 NodeDecision 字段。
- [x] 追踪 `min_level`、`max_level`、`ship_type` 到实际选船逻辑。
- [x] 找出文档、YAML、API 之间的缺失字段和命名差异。
- [x] 复核后端未执行字段在 GUI 中的用途。
- [x] 验证密苏里战列型和导战型的当前舰种识别能力。
- [x] 确认国籍筛选当前只存在于 GUI。
- [x] 将后端 `fleet_presets` 解析收缩为列表校验和三项基础整理。
- [x] 审计上游活动 YAML 新格式及其对统一契约的影响。
- [ ] 确认统一后的正式字段和 Schema 所有权。
- [ ] 修改 AutoWSGR-GUI 的模型、编辑器、保存和 API 转换。
- [ ] 修改 AutoWSGR 的 YAML parser、API schema 和 serializer。
- [ ] 迁移两个项目中的内置 YAML。
- [ ] 增加同一份样例在 GUI、YAML parser、API 三条路径上的契约测试。
- [ ] 更新 `docs/architecture/combat-engine.md` 和使用文档。

## 验收标准

1. 同一份 YAML 通过 GUI 加载和后端直接读取时得到相同的运行时舰队规则。
2. 不允许存在“校验通过但执行时未使用”的公开字段。
3. 不允许未知字段被静默忽略。
4. `min_level`、`max_level` 和 `ship_type` 对已有舰队与新选舰船采用一致的验证语义。
5. 已在 GUI 或后端使用的字段保持原有语义。
6. GUI 与后端使用同一份自动化 Schema 契约测试。
7. 普通和活动 YAML 在 GUI、后端 YAML parser、HTTP API 三条路径中得到相同的
   `chapter`、`map_id`、`entrance` 和 `event_name`。
