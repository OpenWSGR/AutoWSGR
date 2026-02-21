# 快速入门指南

> AutoWSGR v2 新手引导 — 从安装到第一次自动出击。

---

## 1. 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.10 | 推荐 3.11+ |
| Android 模拟器 | 雷电 / MuMu / 蓝叠 | 需开启 ADB 调试 |
| 屏幕分辨率 | 960×540 | 模拟器内分辨率，不是桌面分辨率 |
| adb | 自带或手动安装 | 通常模拟器自带 |

---

## 2. 安装

```bash
# 从源码安装 (开发模式)
git clone https://github.com/huan-yp/Auto-WSGR.git
cd Auto-WSGR
pip install -e ".[dev]"

# 或直接安装
pip install autowsgr
```

---

## 3. 配置文件

创建 `user_settings.yaml`，最小配置：

```yaml
# 模拟器类型: 雷电 / MuMu / 蓝叠
emulator_type: 雷电

# 日志级别
log_level: INFO
```

完整配置项参见 `autowsgr/infra/config.py` 中的 `UserConfig` 类。

---

## 4. 核心概念

### 4.1 分层架构

```
你的脚本
    ↓ 调用
ops (游戏操作层)       ← 你主要使用的 API
    ↓ 组合
combat (战斗引擎)      ← 状态机驱动的战斗流程
    ↓ 使用
ui (页面控制器)        ← 单页面内的操作
    ↓ 依赖
vision (视觉识别)      ← 像素/模板/OCR
emulator (设备控制)    ← ADB 截图/点击
infra (基础设施)       ← 配置/日志/异常
```

### 4.2 关键类型

| 类型 | 用途 | 导入 |
|------|------|------|
| `AndroidController` | 设备控制（截图、点击、滑动） | `from autowsgr.emulator import ADBController` |
| `CombatPlan` | 作战计划（阵型、夜战、节点决策） | `from autowsgr.combat.plan import CombatPlan` |
| `CombatResult` | 战斗结果（状态标记、血量、历史） | `from autowsgr.combat.callbacks import CombatResult` |

---

## 5. 第一个脚本 — Hello World

```python
"""连接模拟器并截图"""
from autowsgr.emulator import ADBController

# 连接设备 (自动检测串口)
ctrl = ADBController(serial="127.0.0.1:5555")
ctrl.connect()

# 截图
screen = ctrl.screenshot()
print(f"截图尺寸: {screen.shape}")  # (540, 960, 3) RGB

# 点击屏幕中心
ctrl.click(0.5, 0.5)

ctrl.disconnect()
```

---

## 6. 导航到任意页面

```python
from autowsgr.emulator import ADBController
from autowsgr.ops import goto_page, identify_current_page

ctrl = ADBController(serial="127.0.0.1:5555")
ctrl.connect()

# 识别当前在哪个页面
page = identify_current_page(ctrl)
print(f"当前页面: {page}")

# 导航到地图页面 (自动规划路径、处理弹窗)
goto_page(ctrl, "地图页面")

# 导航到建造页面
goto_page(ctrl, "建造页面")

# 回到主页面
goto_page(ctrl, "主页面")
```

支持的页面名称:

| 页面 | 名称 |
|------|------|
| 主页面 | `"主页面"` |
| 地图页面 | `"地图页面"` |
| 出征准备 | `"出征准备页面"` |
| 后院 | `"后院页面"` |
| 浴室 | `"浴室页面"` |
| 食堂 | `"食堂页面"` |
| 建造 | `"建造页面"` |
| 强化 | `"强化页面"` |
| 任务 | `"任务页面"` |

---

## 7. 收取远征 & 任务奖励

```python
from autowsgr.ops import collect_expedition, collect_rewards

# 收取远征 (自动重新派遣)
collected = collect_expedition(ctrl)

# 收取任务奖励
rewarded = collect_rewards(ctrl)
```

---

## 8. 执行一次战役

```python
from autowsgr.ops import CampaignConfig, run_campaign

config = CampaignConfig(
    map_index=3,          # 第 3 个战役 (驱逐)
    difficulty="hard",     # 困难模式
    fleet_id=1,           # 第 1 舰队
    formation=2,          # 复纵阵
    night=True,           # 进入夜战
)

results = run_campaign(ctrl, config)
print(f"战役结果: {results[0].flag}")
```

---

## 9. 执行一次常规战

```python
from autowsgr.combat.plan import CombatPlan
from autowsgr.ops import run_normal_fight

# 从 YAML 加载作战计划
plan = CombatPlan.from_yaml("plans/normal_fight/5-4.yaml")

# 执行 5 次
results = run_normal_fight(ctrl, plan, times=5)

for i, r in enumerate(results):
    print(f"第 {i+1} 次: {r.flag.value}")
```

关于作战计划的详细配置，见 [战斗系统使用指南](usage_combat.md)。

---

## 10. 更多功能

| 功能 | 文档 |
|------|------|
| 战斗系统详解 | [usage_combat.md](usage_combat.md) |
| 日常操作指南 | [usage_daily_ops.md](usage_daily_ops.md) |
| 决战模式指南 | [usage_decisive.md](usage_decisive.md) |
| 功能总览与对比 | [feature_overview.md](feature_overview.md) |
| UI 架构说明 | [ui_architecture.md](ui_architecture.md) |

---

## 附录: 从 v1 迁移

如果你之前使用 v1 (autowsgr_legacy)，主要改变：

| v1 写法 | v2 写法 |
|---------|---------|
| `timer = start_script('settings.yaml')` | `ctrl = ADBController(serial=...)` + `ctrl.connect()` |
| `timer.set_page("map_page")` | `goto_page(ctrl, "地图页面")` |
| `BattlePlan(timer, '困难驱逐')` | `CampaignRunner(ctrl, config, matcher)` |
| `NormalFightPlan(timer, '5-4.yaml')` | `NormalFightRunner(ctrl, plan, matcher)` |
| `NormalExercisePlan(timer, ...)` | `ExerciseRunner(ctrl, config, matcher)` |
| `DecisiveBattle(timer)` | `DecisiveController(ctrl, config)` |
| `timer.go_main_page()` | `goto_page(ctrl, "主页面")` |

核心变化：用 `ctrl` (AndroidController) 替代 `timer` (God Object)。
