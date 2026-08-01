# 决战流程优化

## 状态

TODO，本轮只记录问题，不修改决战生产逻辑。

## 目标

- 为决战提供与普通战、活动战同层级的清晰入口。
- 将任务执行参数与持久化决战配置分开。
- 只保留一个默认值来源，避免 API、GUI 和 YAML 相互覆盖。
- 决战流程稳定后移除临时换船算法开关。

## 当前配置冲突

决战配置目前有三层来源：

```text
DecisiveConfig 默认值
→ usersettings.yaml
→ API / GUI 任务参数
```

`DecisiveBase` 使用 `model_dump(exclude_unset=True)` 合并，本意是只有用户
真正提供的任务参数才覆盖 YAML。但 API 请求模型为多个字段设置了默认值，
路由又将这些默认值显式传给 `DecisiveConfig`，因此无法再区分“用户填写”
和“API 自动补全”。

已确认的覆盖问题：

- `chapter` 的 API 默认值 `6` 会覆盖 YAML。
- `level1`、`level2`、`flagship_priority` 在 API 与 `DecisiveConfig` 中的
  默认值不同。
- GUI 缺少舰队配置时发送 `[]`，会覆盖 YAML 中的舰队。
- `use_quick_repair` 的 API 默认 `True` 会覆盖 YAML 的 `False`。
- GUI 未提供 `use_new_fleet_change_algorithm`，但 API 默认 `False`，
  会覆盖 YAML 中设置的 `True`。
- `decisive_rounds` 同时被 API 循环和直接脚本读取，职责重复。

以下字段当前不会被 GUI 覆盖，但 GUI 也无法配置：

- `repair_level`
- `full_destroy`
- `useful_skill`
- `useful_skill_strict`

## 后续方案

1. 默认值只保留在 `DecisiveConfig`。
2. API 决战字段改为可选，只传递请求中真正提供的字段。
3. GUI 不再用空列表表示“未提供舰队配置”。
4. `decisive_rounds` 迁移为任务执行参数，不属于持久化决战策略。
5. 决战配置和流程入口整理到独立模块。
6. 增加 YAML、API、GUI 三条入口的配置优先级回归测试。
7. 决战流程重构完成后删除 `use_new_fleet_change_algorithm` 临时开关。

## 本轮不做

- 不修改现有决战配置合并逻辑。
- 不改变 API 请求模型。
- 不修改 GUI 决战表单。
- 不移动决战状态机或 UI 模块。
