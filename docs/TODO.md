# AutoWSGR TODO 清单

> 自动整理于 2026-02-21，按优先级分类。仅包含新架构 (`autowsgr/`) 和项目配置中的 TODO；
> 旧架构 (`autowsgr_legacy/`) 的 TODO 将随迁移逐步替代，不再单独跟踪。

---

## 🔴 P0 — 核心功能缺失（影响正常运行）

| # | 位置 | 描述 |
|---|------|------|
| 1 | [`autowsgr/combat/engine.py#L356`](../autowsgr/combat/engine.py#L356) | **舰队血量检测未接入**：`_detect_ship_stats()` 当前返回旧值，需接入 `BattlePreparationPage.detect_ship_damage` 的像素检测逻辑 |

## 🟡 P1 — 功能增强（已可运行但不够完善）

| # | 位置 | 描述 |
|---|------|------|
| 5 | [`autowsgr/combat/handlers.py#L349`](../autowsgr/combat/handlers.py#L349) | **战果结算可靠性**：`_handle_result()` 需增强可靠性（等待/重试机制） |
| 6 | [`autowsgr/combat/engine.py#L361`](../autowsgr/combat/engine.py#L361) | **掉落舰船 OCR 识别**：`_get_ship_drop()` 当前返回 `None`，需接入 OCR 识别掉落舰船名 |
| 7 | [`autowsgr/ops/decisive/_controller.py#L233`](../autowsgr/ops/decisive/_controller.py#L233) | **决战副官技能检查**：`_handle_map_ready()` 中未检查副官技能 |
| 8 | [`autowsgr/ops/decisive/_controller.py#L239`](../autowsgr/ops/decisive/_controller.py#L239) | **决战前进点 OCR 识别**：选择前进点时未 OCR 识别可选节点名（如 A1, A2），影响智能决策 |
| 9 | [`autowsgr/ops/decisive/_logic.py#L234`](../autowsgr/ops/decisive/_logic.py#L234) | **决战前进选择策略**：`get_advance_choice()` 当前固定返回 0，需根据地图数据和关键节点信息做更智能的选择 |

## 🟢 P2 — 坐标校准 & UI 精化

| # | 位置 | 描述 |
|---|------|------|
| 10 | [`autowsgr/ui/build_page.py#L89`](../autowsgr/ui/build_page.py#L89) | **建造页面标签坐标**：切换标签的点击坐标为估计值，待实际截图确认 |
| 11 | [`autowsgr/ui/navigation.py#L225`](../autowsgr/ui/navigation.py#L225) | **导航图边坐标**：部分导航边坐标为估计值，需在实际游戏中截图校准 |

## 🔵 P3 — 代码质量 & 工程化

| # | 位置 | 描述 |
|---|------|------|
| 12 | [`pyproject.toml#L100-L104`](../pyproject.toml#L100-L104) | **Ruff 规则临时豁免**：`ANN001/ANN201/ANN202`（类型注解）和 `E722/BLE001/B904/TRY*`（异常处理）规则暂时 ignore，需逐步补齐后移除 |

---

## 旧架构待迁移项（仅供参考）

以下 TODO 存在于 `autowsgr_legacy/` 中，在迁移到新架构时一并处理：

| 位置 | 描述 |
|------|------|
| `autowsgr_legacy/configs.py#L181` | OCR 后端：暂时仅 easyocr 可用 |
| `autowsgr_legacy/configs.py#L191-L193` | 浴室数 / 修理位置数可自动获取 |
| `autowsgr_legacy/configs.py#L386` | 检查逻辑待验证 |
| `autowsgr_legacy/timer/timer.py#L278` | 重新登录逻辑留空 |
| `autowsgr_legacy/timer/controllers/android_controller.py#L383` | 图片列表嵌套列表支持 |
| `autowsgr_legacy/timer/controllers/os_controller.py#L116` | Windows 版本返回语言检查 |
| `autowsgr_legacy/timer/backends/ocr_backend.py#L338` | OCR 参数调优 |
| `autowsgr_legacy/timer/backends/ocr_backend.py#L381` | 单独训练 OCR 模型 |
| `autowsgr_legacy/game/build.py#L57` | 获取建造舰船名称 |
| `autowsgr_legacy/game/get_game_info.py#L263` | 精确血量检测 |
| `autowsgr_legacy/game/get_game_info.py#L297` | 结算时检测逻辑 |
| `autowsgr_legacy/fight/decisive_battle.py#L331` | 修理策略：中破/大破控制 |
| `autowsgr_legacy/fight/decisive_battle.py#L369` | 提高 OCR 单数字识别率 |
| `autowsgr_legacy/fight/decisive_battle.py#L774` | 缺少磁盘报错 |
| `autowsgr_legacy/fight/common.py#L495` | 处理其他设备登录 |
| `autowsgr_legacy/fight/common.py#L693` | 跳过开幕支援动画 |
