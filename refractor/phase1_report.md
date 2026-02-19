# 重构 V2 — 第一阶段报告

> **阶段范围：** 基础设施层（Infra）+ 视觉层（Vision）+ 模拟器层（Emulator）
>
> **完成时间：** 2026-02-19
>
> **当前测试数：** 322 个，全部通过，0 Pylance 错误

---

## 一、总体进度

| 层 | 状态 | 新增源文件 | 新增测试文件 | 测试数 |
|----|------|-----------|-------------|-------|
| Infra（基础设施） | ✅ 完成 | 5 | 4 | ~132 |
| Vision（视觉） | ✅ 完成 | 3 | 2 | ~119 |
| Emulator（模拟器） | ✅ 完成 | 3 | 2 | ~72 |
| UIControl | ⬜ 待开始 | — | — | — |
| GameOps | ⬜ 待开始 | — | — | — |
| Scheduler | ⬜ 待开始 | — | — | — |

---

## 二、基础设施层（Infra）

### 2.1 新增文件

| 文件 | 说明 |
|------|------|
| `autowsgr/types.py` | 全局枚举类型（OSType、EmulatorType、GameAPP、ShipType 等） |
| `autowsgr/infra/__init__.py` | 公开 API 汇总导出 |
| `autowsgr/infra/config.py` | Pydantic v2 配置体系（UserConfig 等 11 个 model） |
| `autowsgr/infra/exceptions.py` | 异常层次体系（AutoWSGRError → 16 个子类） |
| `autowsgr/infra/file_utils.py` | YAML 工具（load_yaml / save_yaml / merge_dicts） |
| `autowsgr/infra/logger.py` | loguru 全局日志配置（setup_logger） |

### 2.2 关键设计决策

- **Pydantic v2 + `frozen=True`**：所有配置对象不可变，防止运行时意外修改。  
- **枚举集中于 `types.py`**：所有带游戏语义的枚举统一在此，供各层引用，避免循环依赖。  
- **`UserConfig._resolve_emulator_defaults`**：validator 中自动填充 serial / path / process_name，让用户配置文件尽量精简。  
- **`EmulatorType.auto_emulator_path`**：Windows 走注册表，macOS 走应用目录；Linux/WSL 强制手动指定，避免静默失败。

### 2.3 测试覆盖

```
testing/test_types.py       — 枚举值、自动检测、参数化位置属性
testing/test_exceptions.py  — 层次关系、消息格式、可被 except 捕获
testing/test_file_utils.py  — load/save/merge roundtrip、递归目录创建
testing/test_config.py      — 各子配置默认值、YAML 加载、冻结检查
testing/test_logger.py      — console only / log_dir / 日志文件写入
```

---

## 三、视觉层（Vision）

### 3.1 新增文件

| 文件 | 说明 |
|------|------|
| `autowsgr/vision/__init__.py` | 公开 API 汇总导出 |
| `autowsgr/vision/matcher.py` | 像素特征识别引擎（PixelChecker 等） |
| `autowsgr/vision/ocr.py` | OCR 引擎抽象（EasyOCR / PaddleOCR 双后端） |

### 3.2 关键设计决策

- **以像素特征替代模板匹配**：旧版本依赖大量 `.png` 模板文件，新版用若干像素坐标 + 期望颜色描述每个页面，省去存储和加载开销，匹配速度更快。
- **坐标全相对化（0.0–1.0）**：`PixelRule`、`PixelChecker`、`crop` 等所有接口均使用相对坐标，内部 `int(x * width)` 换算，与分辨率无关（960×540 / 1920×1080 通用）。
- **MatchStrategy 三策略**：`ALL`（全部匹配）/ `ANY`（至少一条）/ `COUNT`（匹配数 ≥ threshold），支持灵活页面签名。
- **短路优化**：`check_signature` 在 `ALL` 模式下首次失败立即返回；`ANY` 模式下首次成功立即返回，避免遍历全部规则。
- **签名可数据化**：`PixelSignature.to_dict()` / `from_dict()` 支持 YAML 序列化，便于版本管理。
- **OCR 仅抽象接口**：`OCREngine` 是 ABC，具体后端（EasyOCR / PaddleOCR）在 `__init__` 中 lazy import，不影响未安装该库的环境。

### 3.3 测试覆盖

```
testing/test_matcher.py  — Color / PixelRule / PixelSignature / PixelChecker
                           全部 API、三种策略、短路、crop、identify_all、集成场景
testing/test_ocr.py      — OCRResult、_edit_distance、_fuzzy_match、recognize_*
                           系列方法（MockOCREngine 无重量级依赖）
```

---

## 四、模拟器层（Emulator）

### 4.1 新增文件

| 文件 | 说明 |
|------|------|
| `autowsgr/emulator/__init__.py` | 公开 API 汇总导出 |
| `autowsgr/emulator/controller.py` | AndroidController ABC + ADBController 实现 |
| `autowsgr/emulator/os_control.py` | EmulatorProcessManager ABC + Win/Mac/Linux 实现 |

### 4.2 关键设计决策

- **`DeviceInfo(frozen=True, slots=True)`**：连接后设备信息不可变。
- **`AndroidController` ABC 13 个抽象方法**：`connect / disconnect / resolution / screenshot / click / swipe / long_tap / key_event / text / start_app / stop_app / is_app_running / shell`，强制子类实现完整接口。
- **相对坐标 click/swipe**：`int(x * width)` 转换，与 Vision 层保持统一。
- **`_require_device()` 辅助方法**：集中做 `_device is None` 检查并抛出 `EmulatorConnectionError`，消除 Pylance 的 `"X" 不是 "None" 的已知属性` 错误（10 处）。
- **airtest 顶层导入**：`connect_device`, `get_device`, `AdbError`, `DeviceConnectionError`, `Android` 均在模块顶层导入，测试 patch 路径为 `autowsgr.emulator.controller.<name>`。
- **`EmulatorProcessManager`**：三个操作系统实现 + factory `create_emulator_manager`，yunshouji（云手机）在 Windows 实现中 early return，无需路径即可运行。

### 4.3 测试覆盖

```
testing/test_controller.py  — DeviceInfo 冻结/等值、AndroidController ABC 约束
                              ADBController 初始化、坐标转换（多分辨率）、
                              截图 RGB→BGR / 超时 / 重试、按键/文本/应用管理、
                              连接 mock（patch connect_device + get_device）
testing/test_os_control.py  — ABC 约束、restart/wait_until_online 默认实现、
                              create_emulator_manager 工厂、Win/Mac/Linux
                              各管理器及边界条件（路径缺失、进程名缺失等）
```

---

## 五、测试基础设施

```
testing/__init__.py            — 空包标记
testing/conftest.py            — fixtures_dir、tmp_yaml 公共 fixtures
testing/fixtures/.gitkeep      — fixtures 目录占位
```

---

## 六、已知限制与后续注意事项

1. **EasyOCR / PaddleOCR** 未在测试环境安装，`OCREngine.create()` 的真实后端用 `importlib.util.find_spec` 跳过测试；实际使用需安装相应 Python 包。
2. **airtest** 在测试中 mock，不需要真实设备；CI 环境可正常运行所有 322 个测试。
3. **Windows 注册表路径**（`EmulatorType._windows_auto_emulator_path`）：针对雷电、蓝叠、MuMu 三款主流模拟器；其他模拟器需用户手动配置 `emulator.path`。
4. **WSL 环境**：`serial` 和 `path` 必须显式配置（`UserConfig._resolve_emulator_defaults` 中会校验），不支持自动检测。

---

## 七、第二阶段计划

下一步：**UIControl 层**

- 读取 `refractor/04_ui_control.md` 设计规范
- 实现 `UIRecognizer`（基于 PixelChecker / OCREngine 的页面识别）
- 实现 `UIController` 基类 + 具体页面 Controller
- 实现 `UIAction`（带重试/超时的操作原语）
- 对应测试文件 `testing/test_ui_*.py`
