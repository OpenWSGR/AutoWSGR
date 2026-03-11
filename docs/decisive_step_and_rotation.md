# 决战 (Decisive) 增强方案: step 模式与全局舰船状态

## 1. 目标

1. **step 模式**: 导出 `step()`, 每次只推进到下一个战斗节点完成并返回,
   上层可在节点间插入自定义调度 (送修、换船等).
2. **全局舰船状态**: 通过 context 层维护舰船破损/修理中状态,
   `get_best_fleet` 自动排除不可用舰船 (大破 + 修理中),
   用剩余舰船组成次优编队.
3. **轮修由上层调度**: 决战控制器不涉及修理决策,
   只负责"排除不可用舰船后组编队".

---

## 2. 现状问题

- `get_best_fleet()` 不感知舰船血量, 无法排除大破/修理中舰船.
- 舰船名与血量的对应靠 `state.fleet` 位置索引隐式绑定,
  没有全局的 name -> state 映射.
- `Ship` 模型没有 "修理中" 标记.
- `run()` 一次跑完整轮, 无法在节点间介入.

---

## 3. 方案

### 3.1 context 层: Ship 增加可用性判断

`Ship` 新增 `repairing: bool` 字段和 `available` 属性.
`available` 聚合 "非大破 且 非修理中" 两个条件.
`repairing` 由上层设置/清除, 决战只读.

### 3.2 context 层: GameContext 舰船注册表

GameContext 新增 `ship_registry: dict[str, Ship]`,
提供 `get_ship` / `update_ship_damage` / `is_ship_available` 等接口,
供各 ops 统一查询和更新舰船状态.

### 3.3 决战状态同步

handlers 中新增 `_sync_ship_states()`,
在以下时机把 `ship_stats[i]` 写入 `ctx.ship_registry[fleet[i+1]]`:

- 战斗结束后 (`_handle_combat`)
- 血量检测后 (`_handle_prepare_combat`)
- 恢复模式扫描后 (`check_fleet`)

### 3.4 get_best_fleet 自动排除

`DecisiveLogic` 注入 `ctx` 引用,
`get_best_fleet()` 遍历候选舰船时加 `ctx.is_ship_available(name)` 过滤.
不需要额外的 `exclude` 参数 -- 上层通过设置 ship 状态来控制.

### 3.5 step() 接口

从 `_main_loop` 抽取 `_dispatch_phase()`, `run()` 和 `step()` 共用.
`step()` 首次调用时自动初始化, 之后每次推进到一个战斗节点完成后返回.

返回 `StepInfo(result, stage, node, ship_stats, fleet)`,
其中 `result` 为 `StepResult` 枚举
(NODE_COMPLETE / STAGE_CLEAR / CHAPTER_CLEAR / RETREAT / LEAVE / ERROR).

暂停点: NODE_RESULT 处理完成后、STAGE_CLEAR、终止阶段.
`_handle_node_result` 中的推进和 overlay 检测需拆分,
step 在推进完成后返回, 下次调用再做 overlay 检测.

---

## 4. 数据流

```
战斗结束
  -> handlers: ship_stats 同步到 ctx.ship_registry
  -> step() 返回 StepInfo

上层:
  -> 查 ctx.get_ship(name).damage_state
  -> 若需送修: ship.repairing = True
  -> 修完: ship.repairing = False, 更新 damage_state

下次 step():
  -> get_best_fleet() 自动跳过 repairing / SEVERE 的舰船
  -> 组成次优编队继续战斗
```

---

## 5. 注意事项

- step() 暂停时状态必须自洽: node 已推进, ship_stats 已同步, fleet 反映实际编队.
- 恢复模式 (resume_mode) 首次进入时需完整扫描并同步到 ctx.
- 排除舰船后 `change_fleet()` 逻辑不变, `get_best_fleet()` 内部已过滤.
- 上层修理契约: 送修时设 `repairing = True`, 修完后清除并更新 `damage_state`.
- 决战内快速修理使用决战资源, 修理后由 `_sync_ship_states` 在下次检测时自动同步.
