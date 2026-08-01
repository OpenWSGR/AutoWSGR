# 决战换船算法开关

## 状态

代码已完成，待决战实机验证。

## 目标

新的换船算法先在常规出征中使用，决战是否启用由独立开关控制。
关闭开关不会停止决战，而是继续使用原有的决战换船和 OCR 流程。

## 配置

```yaml
decisive_battle:
  use_new_fleet_change_algorithm: false
```

- `false`：默认值，使用原有决战换船流程。
- `true`：决战使用新的换船算法。

API 请求支持同名字段。

## 原有决战 OCR 流程

1. 准备页调用 `detect_fleet()`，从六个槽位的舰名区域识别当前舰队。
2. 不传 `expected_names`，不使用新算法提供的目标舰名上下文。
3. 决战选船页没有搜索框，通过 DLL 定位舰船行，再使用 OCR 匹配并点击。
4. 完成成员替换和顺序调整后，再次 OCR 验证结果。

`ship_name_match_confidence` 是独立的 OCR feat。该配置启用时，
原有决战流程仍会使用共享 OCR 模块中的置信度匹配。

## 代码改动

- `DecisiveConfig` 和决战 API 请求增加 `use_new_fleet_change_algorithm`。
- `DecisiveBattlePreparationPage.change_fleet()` 根据开关选择算法。
- `legacy_fleet_change.py` 保留原有决战换船流程。
- 新换船算法本身不处理开关，避免常规出征受到影响。

## 验证

- 单元测试确认默认使用原有流程。
- 单元测试确认开启后使用新算法。
- 单元测试确认原有流程调用 OCR 时不传目标舰名上下文。

## TODO

- 在决战环境中分别实测开关关闭和开启。
- 实机确认旧流程的舰队识别、直接列表选船和顺序调整。
- 决战入口独立重构见 `feat-refactor-decisive-fight-module.md`。
