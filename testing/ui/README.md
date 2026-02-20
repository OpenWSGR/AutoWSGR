# UI 控制器测试说明

`testing/ui/` 下每个 UI 控制器对应一个子目录，目录内包含两类测试：

| 文件 | 类型 | 运行方式 | 需要真实设备 |
|---|---|---|---|
| `test_unit.py` | 单元测试（mock） | `pytest` | 否 |
| `e2e.py` | 端到端测试（真实设备） | 直接执行 | **是** |

---

## 单元测试

```bash
pytest testing/ui/
```

不需要连接设备，由 CI 自动运行。

---

## 端到端测试 (e2e)

### 一键运行所有测试

运行汇总脚本一次执行所有 12 个 e2e 测试：

**Python（跨平台）**：

```bash
# 自动检测设备，序列运行所有测试
python testing/ui/run_all_e2e.py

# 指定设备并启用调试
python testing/ui/run_all_e2e.py --serial emulator-5554 --debug

# 自定义等待时间（每步 2 秒）
python testing/ui/run_all_e2e.py --pause 2.0

# 指定汇总报告输出路径
python testing/ui/run_all_e2e.py --output my_report.json
```

**PowerShell（Windows）**：

```powershell
# 自动检测设备，序列运行所有测试
.\testing\ui\run_all_e2e.ps1

# 指定设备
.\testing\ui\run_all_e2e.ps1 -Serial emulator-5554 -Debug

# 自定义等待时间
.\testing\ui\run_all_e2e.ps1 -Pause 2.0

# 指定输出路径
.\testing\ui\run_all_e2e.ps1 -Output my_report.json
```

脚本会：

1. 自动搜索所有 `testing/ui/*/e2e.py` 脚本
2. 按顺序执行（--parallel 参数当前为预留，实装为序列）
3. 自动启用 `--auto` 模式（不等待用户输入）
4. 收集每个测试的退出码、日志路径、耗时
5. 输出统一汇总（通过个数 / 失败个数 / 总耗时）
6. 保存 JSON 格式的详细报告到 `logs/e2e_summary.json`

**返回值**：
- `0` — 全部测试通过
- `1` — 存在失败的测试

**输出示例**：

```
════════════════════════════════════════════════════════════════════
  自动化 e2e 测试运行 (找到 12 个测试)
════════════════════════════════════════════════════════════════════

  设备    : 自动检测
  调试    : 禁用
  等待    : 1.5s
  并行    : 1

[1/12] 运行 main_page                ✓ PASS                (12.3s)
[2/12] 运行 map_page                 ✓ PASS                (28.5s)
...
[12/12] 运行 battle_preparation      ✗ FAIL(exit 1)        (5.2s)

════════════════════════════════════════════════════════════════════
  e2e 测试汇总
════════════════════════════════════════════════════════════════════

  ✓ main_page                  exit=  0    12.3s
  ✓ map_page                   exit=  0    28.5s
  ...
  ✗ battle_preparation         exit=  1     5.2s

  总计: 12 个测试
  通过: 11 个 (92%)
  失败: 1 个
  耗时: 125.8s

  ✗ 1 个测试失败

  失败测试列表:
    - battle_preparation (exit 1)
════════════════════════════════════════════════════════════════════
  报告已保存: logs/e2e_summary.json
```

### 单个测试运行

### 前置条件

1. 已安装 ADB，且 `adb devices` 能看到目标设备（模拟器或手机）
2. 游戏已启动并处于对应页面（每个脚本的 **前置条件** 见下表）
3. 已安装项目依赖：`pip install -e .`

### 通用命令格式

```
python testing/ui/<page>/e2e.py [serial] [--auto] [--debug] [--pause SECONDS]
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `serial` | ADB 设备序列号（如 `emulator-5554`） | 自动检测 |
| `--auto` | 全自动执行，不等待按键确认 | 关（交互模式） |
| `--debug` | 日志级别设为 DEBUG | 关 |
| `--pause SECONDS` | 每步操作后等待时间（秒） | `1.5` |

### 运行示例

```bash
# 交互模式，自动检测设备
python testing/ui/main_page/e2e.py

# 自动模式，指定设备序列号
python testing/ui/main_page/e2e.py emulator-5554 --auto

# 调试详细日志，动作间隔 2 秒
python testing/ui/map_page/e2e.py --auto --debug --pause 2.0
```

---

## 交互模式 vs 自动模式

两种模式均在连接设备后**立即**开始执行，不再等待人工按键。

### 自动导航（公共行为）

每个脚本启动后，`ensure_page` 会自动处理前置页面：

1. **检测当前页面** — 已在目标页面则直接开始测试
2. **尝试自动导航** — 从已知入口（主页面/侧边栏/后院）自动导航到目标页面
3. **处理导航失败**：
   - **交互模式**：打印提示，等待用户手动切换后按 Enter 确认，循环检测
   - **自动模式**：打印错误，退出（exit code 1）

| 控制器 | 自动导航路径 |
|---|---|
| `main_page` | 尝试从地图/侧边栏/后院/任务调用 `go_back()` |
| `map_page` | 主页面 → `go_to_sortie()` |
| `sidebar_page` | 主页面 → `open_sidebar()` |
| `backyard_page` | 主页面 → `go_home()` |
| `mission_page` | 主页面 → `go_to_task()` |
| `build_page` | 主页面 → 侧边栏 → `go_to_build()` |
| `intensify_page` | 主页面 → 侧边栏 → `go_to_intensify()` |
| `friend_page` | 主页面 → 侧边栏 → `go_to_friend()` |
| `bath_page` | 主页面 → 后院 → `go_to_bath()` |
| `canteen_page` | 主页面 → 后院 → `go_to_canteen()` |
| `decisive_battle_page` | 主页面 → 地图 → 切换决战面板 → `MapPage.enter_decisive()` |
| `battle_preparation` | 主页面 → 地图（需人工选关卡进入） |

### 交互模式（默认）

成功进入目标页面后，每个步骤执行前显示提示：

```
──────────────────────────────────────────────────────────────────────
  [001] 初始验证: 主页面
──────────────────────────────────────────────────────────────────────
  [Enter] 执行  |  [s] 跳过  |  [q] 退出:
```

- <kbd>Enter</kbd> — 执行该步骤
- <kbd>s</kbd> + <kbd>Enter</kbd> — 跳过，记录为 `skip`
- <kbd>q</kbd> + <kbd>Enter</kbd> — 终止后续步骤，直接进入汇总

适合手动调试，可在每步之间自行操作游戏。若自动导航失败，交互模式会在此额外等待用户手动切换页面。

### 自动模式（`--auto`）

所有步骤连续执行，不等待确认。适合回归验证。

---

## 各控制器覆盖范围

| 脚本 | 前置页面 | 测试步骤概要 |
|---|---|---|
| `main_page/e2e.py` | 主页面（母港） | 验证识别 → 读状态 → 跳转地图/任务/侧边栏/后院并返回 |
| `map_page/e2e.py` | 地图选择页（出征面板） | 验证识别 → 读状态 → 5个面板切换 → 章节前进/后退 → 返回主页面 |
| `sidebar_page/e2e.py` | 侧边栏 | 验证识别 → 进入建造（4标签）→ 进入强化（3标签）→ 进入好友 → 关闭返回主页面 |
| `backyard_page/e2e.py` | 后院 | 验证识别 → 进浴室并返回 → 进食堂并返回 → 返回主页面 |
| `mission_page/e2e.py` | 任务页面 | 验证识别 → 返回主页面 |
| `build_page/e2e.py` | 建造页面（侧边栏进入） | 验证识别 → 读当前标签 → 4标签切换 → 返回侧边栏 |
| `intensify_page/e2e.py` | 强化页面（侧边栏进入） | 验证识别 → 读当前标签 → 3标签切换 → 返回侧边栏 |
| `friend_page/e2e.py` | 好友页面（侧边栏进入） | 验证识别 → 返回侧边栏 |
| `bath_page/e2e.py` | 浴室（后院进入） | 验证识别 → 读修理状态 → 返回后院 |
| `canteen_page/e2e.py` | 食堂（后院进入） | 验证识别 → 返回后院 |

---

## 输出

### 终端输出

每步显示结果符号：

```
  ✓ 页面验证通过: 地图页面
  ✗ 页面验证失败: 期望'主页面', 实际'?'
  ℹ 报告已保存: logs/e2e/main_page/e2e_report_主页面.json
```

### 汇总表格

脚本结束时打印：

```
════════════════════════════════════════════════════════════════════
  主页面 — e2e 测试结果汇总

  ✓ [001] 初始验证: 主页面                          pass     123ms  [主页面]
  ✓ [002] 主页面 → 地图页面 (出征)                  pass     856ms  [地图选择]
  ...

  总计: 7 步  通过: 7  失败: 0  跳过: 0  异常: 0

  ✓ 全部通过!
════════════════════════════════════════════════════════════════════
```

### 截图和 JSON 报告

所有截图和结构化报告保存在 `logs/e2e/<page>/` 目录（可通过 `--pause` 所在脚本的 `default_log_dir` 自定义）：

```
logs/e2e/main_page/
  001_verify_主页面.png
  002_主页面to地图页面(出征).png
  ...
  e2e_report_主页面.json
```

JSON 报告格式：

```json
{
  "controller": "主页面",
  "mode": "auto",
  "total_steps": 7,
  "passed": 7,
  "failed": 0,
  "steps": [
    {
      "index": 1,
      "action": "初始验证: 主页面",
      "expected_page": "主页面",
      "actual_page": "主页面",
      "page_check": true,
      "result": "pass",
      "screenshot_path": "logs/e2e/main_page/001_verify_主页面.png",
      "duration_ms": 123
    }
  ]
}
```

### 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 全部通过（含有跳过步骤也视为成功） |
| `1` | 存在 `fail` 或 `error` 步骤 |

---

## 补充说明

- `e2e.py` 文件名不以 `test_` 开头，**不会被 `pytest` 自动收集**，避免无设备的 CI 环境误触发。
- 若要在 CI 中运行 e2e，需显式调用 `python testing/ui/<page>/e2e.py --auto`，并确保 ADB 已连接。
- 每次测试只覆盖**单个控制器**，适合在修改对应页面逻辑后做针对性回归。
