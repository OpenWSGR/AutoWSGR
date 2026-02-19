# 基础设施层 (Infrastructure)

## 职责

提供与游戏逻辑完全无关的基础能力：日志、配置加载/校验、异常体系、文件工具。

---

## 1. Logger

### 现状问题

```python
# 当前代码：包装 loguru 但引入了 bug
class Logger:
    def debug(self, *args, sep=' '):
        debug_str = sep.join(args)  # args 含非 str 时 TypeError
```

### 新设计

不再包装 loguru，直接使用。提供一个配置函数：

```python
# autowsgr/infra/logger.py

import sys
from pathlib import Path
from loguru import logger


def setup_logger(
    log_dir: Path | None = None,
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """配置全局 loguru logger"""
    logger.remove()
    
    # 控制台输出
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level:8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
    )
    
    # 文件输出
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "autowsgr_{time:YYYY-MM-DD}.log",
            level=level,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
        )


# 全局 logger 直接 from loguru import logger 使用
# 各模块: from loguru import logger
```

**使用方式：**
```python
from loguru import logger

logger.info("开始出征 章节={} 地图={}", chapter, map_id)
logger.warning("检测到网络异常，重试第 {} 次", retry)
```

---

## 2. ConfigManager

### 现状问题

- `BaseConfig` 是 frozen dataclass 但到处 `object.__setattr__`
- `UserConfig.__post_init__` 有 20+ 行 `object.__setattr__`
- 嵌套配置用 `ATTRIBUTE_RECURSIVE` 全局 dict 处理
- 配置校验逻辑散落在 `__post_init__`

### 新设计

使用 Pydantic v2 BaseModel：

```python
# autowsgr/infra/config.py

from pathlib import Path
from pydantic import BaseModel, field_validator, model_validator
from loguru import logger


class EmulatorConfig(BaseModel):
    """模拟器配置"""
    type: str = "雷电"                      # 模拟器类型
    path: Path | None = None                 # 模拟器安装路径（None = 自动检测）
    serial: str | None = None                # ADB serial（None = 自动检测）
    
    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {"雷电", "蓝叠", "MuMu", "逍遥", "夜神", "自定义"}
        if v not in valid:
            raise ValueError(f"不支持的模拟器: {v}, 可选: {valid}")
        return v


class AccountConfig(BaseModel):
    """游戏账号配置"""
    game_app: str = "官服"                   # 官服/渠道服/小服
    account: str = ""
    password: str = ""


class OCRConfig(BaseModel):
    """OCR 引擎配置"""
    engine: str = "easyocr"                  # easyocr / paddleocr
    gpu: bool = False


class LogConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    dir: Path = Path("log")


class DailyConfig(BaseModel):
    """日常自动化设置"""
    exercise: bool = True
    exercise_fleet_id: int = 4
    expedition: list[int] = [5, 7, 21, 36]
    battle: bool = False
    battle_fleet_id: int = 4


class UserConfig(BaseModel):
    """用户配置（顶层）"""
    emulator: EmulatorConfig = EmulatorConfig()
    account: AccountConfig = AccountConfig()
    ocr: OCRConfig = OCRConfig()
    log: LogConfig = LogConfig()
    daily: DailyConfig = DailyConfig()
    
    # 通用行为设置
    dock_full_destroy: bool = True
    ship_names: list[str] = []
    
    @classmethod
    def from_yaml(cls, path: Path) -> "UserConfig":
        """从 YAML 文件加载"""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)


class ConfigManager:
    """配置管理器"""
    
    @staticmethod
    def load(path: str | Path) -> UserConfig:
        path = Path(path)
        if not path.exists():
            logger.warning("配置文件 {} 不存在，使用默认配置", path)
            return UserConfig()
        
        config = UserConfig.from_yaml(path)
        logger.info("已加载配置: {}", path)
        return config
```

**YAML 配置文件示例：**
```yaml
emulator:
  type: "雷电"
  path: null     # 自动检测

account:
  game_app: "官服"
  account: ""
  password: ""

ocr:
  engine: "easyocr"
  gpu: false

log:
  level: "INFO"
  dir: "log"

daily:
  exercise: true
  exercise_fleet_id: 4
  expedition: [5, 7, 21, 36]

dock_full_destroy: true
ship_names:
  - "胡德"
  - "俾斯麦"
```

---

## 3. 异常体系

### 现状问题

```python
# 全部继承 BaseException（应该是 Exception）
class CriticalErr(BaseException): ...
class ImageNotFoundErr(BaseException): ...
class NetworkErr(BaseException): ...
class LogitException(BaseException):
    def __init__(self, *args):
        super().__init__()(*args)  # BUG: 调用了 None
```

### 新设计

```python
# autowsgr/infra/exceptions.py


class AutoWSGRError(Exception):
    """所有 AutoWSGR 异常的基类"""
    pass


# ── 基础设施异常 ──

class ConfigError(AutoWSGRError):
    """配置错误（文件缺失、字段非法等）"""
    pass


class EmulatorError(AutoWSGRError):
    """模拟器操作失败"""
    pass


class EmulatorConnectionError(EmulatorError):
    """模拟器连接失败"""
    pass


class EmulatorNotFoundError(EmulatorError):
    """未检测到模拟器"""
    pass


# ── 视觉层异常 ──

class VisionError(AutoWSGRError):
    """视觉识别相关错误"""
    pass


class ImageNotFoundError(VisionError):
    """图像模板匹配超时"""
    def __init__(self, template_name: str = "", timeout: float = 0):
        self.template_name = template_name
        self.timeout = timeout
        super().__init__(f"未找到图像 '{template_name}'（超时 {timeout:.1f}s）")


class OCRError(VisionError):
    """OCR 识别失败"""
    pass


# ── UI 层异常 ──

class UIError(AutoWSGRError):
    """UI 操作相关错误"""
    pass


class PageNotFoundError(UIError):
    """无法识别当前页面"""
    pass


class NavigationError(UIError):
    """页面导航失败"""
    def __init__(self, source: str, target: str, reason: str = ""):
        self.source = source
        self.target = target
        super().__init__(f"导航失败: {source} → {target}" + (f" ({reason})" if reason else ""))


class ActionFailedError(UIError):
    """UIAction 执行失败"""
    def __init__(self, action_name: str, reason: str = ""):
        self.action_name = action_name
        super().__init__(f"操作失败: {action_name}" + (f" ({reason})" if reason else ""))


# ── 游戏逻辑异常 ──

class GameError(AutoWSGRError):
    """游戏逻辑错误"""
    pass


class NetworkError(GameError):
    """游戏网络错误（断线、卡顿）"""
    pass


class DockFullError(GameError):
    """船坞已满"""
    pass


class ResourceError(GameError):
    """资源不足"""
    pass


class CriticalError(AutoWSGRError):
    """不可恢复的严重错误，需要终止"""
    pass
```

**异常层级树：**
```
AutoWSGRError
├── ConfigError
├── EmulatorError
│   ├── EmulatorConnectionError
│   └── EmulatorNotFoundError
├── VisionError
│   ├── ImageNotFoundError
│   └── OCRError
├── UIError
│   ├── PageNotFoundError
│   ├── NavigationError
│   └── ActionFailedError
├── GameError
│   ├── NetworkError
│   ├── DockFullError
│   └── ResourceError
└── CriticalError
```

---

## 4. 文件工具

```python
# autowsgr/infra/file_utils.py

from pathlib import Path
from typing import Any
import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """加载 YAML 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_dicts(base: dict, override: dict) -> dict:
    """深度合并字典，override 优先"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
```
