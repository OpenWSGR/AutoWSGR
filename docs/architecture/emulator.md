# 模拟器连接层

> 返回 [架构概述](README.md)

本文档描述 AutoWSGR 如何连接和控制 Android 模拟器。

---

## 双层架构

```
┌───────────────────────────────────────┐
│  AndroidController (协议/接口)         │  截图 + 触控 + 应用管理
│    └─ ScrcpyController (实现)         │  基于 scrcpy 协议
├───────────────────────────────────────┤
│  EmulatorProcessManager (抽象)        │  进程启停
│    ├─ WindowsEmulatorManager          │  注册表路径查找
│    ├─ MacEmulatorManager              │
│    └─ LinuxEmulatorManager            │
├───────────────────────────────────────┤
│  detector.py                          │  ADB 设备自动检测
└───────────────────────────────────────┘
```

---

## AndroidController 协议

**文件**: `autowsgr/emulator/controller/__init__.py`

所有设备操作通过此协议访问，上层代码不关心具体实现。

```python
class AndroidController(Protocol):
    def connect() -> DeviceInfo
    def disconnect() -> None
    def screenshot() -> np.ndarray        # HxWx3, RGB, uint8
    def click(x: float, y: float) -> None # 归一化坐标 (0-1)
    def swipe(x1, y1, x2, y2, duration) -> None
    def key(key_code: int) -> None
    def input_text(text: str) -> None
    def is_app_running(package: str) -> bool
    def start_app(package: str, activity: str) -> None
    def stop_app(package: str) -> None
```

### 坐标体系

所有坐标使用 **归一化相对值**（0.0 ~ 1.0）：

- `(0.0, 0.0)` = 左上角
- `(1.0, 1.0)` = 右下角
- `(0.5, 0.5)` = 屏幕正中

这使得代码不依赖具体分辨率，模板图片采集基准为 960x540。

### 截图格式

`screenshot()` 返回 `numpy.ndarray`：

- 形状: `(H, W, 3)` — 高度 x 宽度 x 3通道
- 通道顺序: **RGB**（非 OpenCV 默认的 BGR）
- 数据类型: `uint8`

---

## ScrcpyController

**文件**: `autowsgr/emulator/controller/scrcpy.py`

基于 scrcpy 协议的 `AndroidController` 实现。通过 ADB 推送 `scrcpy-server.jar` 到设备，建立视频流获取截图，通过 ADB 控制输入。

### 构造

```python
ctrl = ScrcpyController(
    serial='emulator-5554',   # ADB serial，可为 None (自动检测)
    config=emulator_config,    # EmulatorConfig
    package_name='com.huanmeng.zhanjian2',  # 按游戏包名选择显示屏
)
ctrl.connect()  # → DeviceInfo(resolution, device_name)
```

### MuMu 等多显示屏模拟器

新版 MuMu 可能将游戏放在独立的 Android 显示屏上，而 0 号屏仍显示启动器。
`Launcher` 会传入账号渠道的游戏包名；控制器先检查游戏进程，再从
`dumpsys activity activities` 的逐屏活动列表定位游戏，优先使用已恢复的游戏活动。
游戏进程不存在时使用 0 号屏，避免应用停止后残留的活动记录指向旧显示屏。
启动应用前会先关闭旧视频与触控连接，避免 MuMu 把新活动放到临时镜像屏；
启动后和视频流重连时会重新检测，正常截图期间最多每 2 秒检测一次，
屏幕编号改变时同时重建视频与触控连接。因此无需将某次运行的编号写死。

默认配置使用自动检测，也可为特殊设备手动指定非负的显示屏编号：

```yaml
emulator:
  display_id: null  # 默认：按游戏包名自动检测；0 表示固定使用默认屏
```

手动编号优先于自动检测。直接使用 `ScrcpyController` 时，在构造函数传入
`package_name`，或通过 `start_app(package)` 设置跟踪的包名。
视频和触控通过同一个 scrcpy server 的 `display_id` 指向相同显示屏；
重建连接时会关闭旧 socket、等待解码线程退出，并丢弃旧帧。

### 连接流程

```
ScrcpyController(serial, config)
       │
       ▼
  connect()
    ├─ serial 为 None → detector.resolve_serial(config)
    ├─ adb connect {serial}
    ├─ 推送 scrcpy-server.jar (从 data/bin/ 加载)
    ├─ 启动 scrcpy server 进程
    ├─ 建立视频流连接
    └─ 返回 DeviceInfo
```

---

## 设备检测

**文件**: `autowsgr/emulator/detector.py`

当用户未指定 ADB serial 时，自动检测已连接的设备。

### detect_emulators()

运行 `adb devices`，逐行解析输出，根据 serial 格式推断模拟器类型：

| serial 模式           | 推断类型  |
|----------------------|----------|
| `emulator-NNNN`     | 雷电      |
| `127.0.0.1:16384+`  | MuMu     |
| `127.0.0.1:5555+`   | 蓝叠      |

### resolve_serial(config)

解析最终使用的 serial：

```
config.serial 已指定？ → 直接使用
           │ No
           ▼
  仅检测到 1 个设备？ → 自动选择
           │ No
           ▼
  多设备中类型匹配唯一？ → 自动选择
           │ No
           ▼
  抛出异常 / CLI 提示选择
```

---

## 进程管理

**文件**: `autowsgr/emulator/os_control/`

平台相关的模拟器进程管理。

### 平台差异

| 平台      | 路径查找方式              | 支持的模拟器       |
|-----------|------------------------|--------------------|
| Windows   | 注册表 (`winreg`)       | 雷电、蓝叠、MuMu   |
| macOS     | 固定路径 `/Applications/` | MuMu、蓝叠        |
| Linux/WSL | 未实现                   | -                  |

Windows 注册表路径示例：

- 雷电: `HKLM\SOFTWARE\leidian\{version}\InstallDir`
- 蓝叠: `HKLM\SOFTWARE\BlueStacks_nxt_cn\InstallDir`
- MuMu: `HKLM\SOFTWARE\...\Uninstall\MuMuPlayer-12.0\UninstallString`

### EmulatorProcessManager 接口

```python
class EmulatorProcessManager(ABC):
    def start() -> None       # 启动模拟器进程
    def stop() -> None        # 停止模拟器进程
    def is_running() -> bool  # 检查进程是否运行

create_emulator_manager(emulator_type, os_type) -> EmulatorProcessManager
```

---

## 与其他模块的关系

- **构造者**: [scheduler](scheduler-and-server.md) 的 `Launcher.connect()` 创建 `ScrcpyController`
- **消费者**: [vision](vision.md) 层通过 `ctrl.screenshot()` 获取截图
- **消费者**: [ui](ui.md) 层通过 `ctrl.click()` / `ctrl.swipe()` 执行触控
- **消费者**: [ops](ops.md) 层通过 `ctrl.start_app()` / `ctrl.stop_app()` 管理游戏进程
- **配置来源**: [context-and-config](context-and-config.md) 的 `EmulatorConfig` 提供连接参数

---

## 开发注意事项

1. **截图性能**: scrcpy 视频流解码有一定延迟，`screenshot()` 返回的是最近一帧。性能基准测试可用 `tools/benchmark_emulator.py`
2. **连接稳定性**: 模拟器重启后 ADB 连接可能断开，需重新 `connect()`
3. **坐标转换**: 所有上层代码使用归一化坐标 (0-1)，`ScrcpyController` 内部按实际分辨率转换为像素坐标
4. **二进制资源**: `scrcpy-server.jar` 打包在 `data/bin/` 中，`pip install` 时随包分发
