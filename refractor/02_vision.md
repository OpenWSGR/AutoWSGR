# 视觉层 (Vision)

## 职责

提供纯粹的图像/文本识别能力，不包含任何游戏逻辑或设备操作。

给定一张图片（numpy 数组），返回识别结果：
- **ImageMatcher**: 模板匹配 → 是否存在 / 位置 / 置信度
- **OCREngine**: 文字识别 → 文字内容 / 数字

---

## 1. ImageMatcher

### 现状问题

图像匹配逻辑散落在 `AndroidController`：
- `image_exist()` — 返回 bool
- `wait_image()` — 阻塞等待并返回位置
- `wait_images()` — 阻塞等待多个模板，返回索引（-1 或从 0 开始，语义混乱）
- `get_image_position()` — 获取匹配位置
- `check_pixel()` — 像素颜色检查

这些方法既做截图（设备操作）又做匹配（视觉识别），违反单一职责。

### 新设计

```python
# autowsgr/vision/matcher.py

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import cv2
from loguru import logger


@dataclass(frozen=True)
class MatchResult:
    """匹配结果"""
    found: bool
    confidence: float = 0.0
    position: tuple[int, int] | None = None  # 匹配位置 (x, y)
    
    def __bool__(self) -> bool:
        return self.found


@dataclass(frozen=True)
class Color:
    """BGR 颜色（OpenCV 默认格式）"""
    b: int
    g: int
    r: int
    
    def distance(self, other: "Color") -> float:
        return ((self.b - other.b) ** 2 + (self.g - other.g) ** 2 + (self.r - other.r) ** 2) ** 0.5
    
    @classmethod
    def from_bgr(cls, bgr: tuple[int, int, int]) -> "Color":
        return cls(b=bgr[0], g=bgr[1], r=bgr[2])
    
    @classmethod
    def from_rgb(cls, rgb: tuple[int, int, int]) -> "Color":
        return cls(b=rgb[2], g=rgb[1], r=rgb[0])


class ImageMatcher:
    """图像模板匹配引擎"""
    
    def __init__(self, default_confidence: float = 0.85) -> None:
        self._default_confidence = default_confidence
        self._template_cache: dict[str, np.ndarray] = {}
    
    # ── 核心方法 ──
    
    def match(
        self,
        screen: np.ndarray,
        template: np.ndarray,
        confidence: float | None = None,
    ) -> MatchResult:
        """单模板匹配"""
        conf = confidence or self._default_confidence
        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= conf:
            return MatchResult(found=True, confidence=max_val, position=max_loc)
        return MatchResult(found=False, confidence=max_val)
    
    def match_any(
        self,
        screen: np.ndarray,
        templates: list[np.ndarray],
        confidence: float | None = None,
    ) -> tuple[int, MatchResult]:
        """多模板匹配，返回 (索引, 结果)。全部未匹配时索引为 -1"""
        for i, tpl in enumerate(templates):
            result = self.match(screen, tpl, confidence)
            if result:
                return i, result
        return -1, MatchResult(found=False)
    
    def match_best(
        self,
        screen: np.ndarray,
        templates: list[np.ndarray],
    ) -> tuple[int, MatchResult]:
        """多模板匹配，返回置信度最高的"""
        best_idx = -1
        best_result = MatchResult(found=False)
        for i, tpl in enumerate(templates):
            result = self.match(screen, tpl, confidence=0.0)
            if result.confidence > best_result.confidence:
                best_idx = i
                best_result = result
        return best_idx, best_result
    
    # ── 像素操作 ──
    
    @staticmethod
    def get_pixel(screen: np.ndarray, x: int, y: int) -> Color:
        """获取指定位置的像素颜色 (BGR)"""
        bgr = screen[y, x]
        return Color(b=int(bgr[0]), g=int(bgr[1]), r=int(bgr[2]))
    
    @staticmethod
    def check_pixel(
        screen: np.ndarray,
        x: int, y: int,
        expected: Color,
        tolerance: float = 20.0,
    ) -> bool:
        """检查像素颜色是否接近预期值"""
        actual = ImageMatcher.get_pixel(screen, x, y)
        return actual.distance(expected) <= tolerance
    
    # ── 图像裁切 ──
    
    @staticmethod
    def crop(
        screen: np.ndarray,
        x1: int, y1: int,
        x2: int, y2: int,
    ) -> np.ndarray:
        """裁切图像区域"""
        return screen[y1:y2, x1:x2].copy()
    
    # ── 模板加载 ──
    
    def load_template(self, path: Path) -> np.ndarray:
        """加载模板图片（带缓存）"""
        key = str(path)
        if key not in self._template_cache:
            img = cv2.imread(str(path))
            if img is None:
                raise FileNotFoundError(f"模板文件不存在: {path}")
            self._template_cache[key] = img
        return self._template_cache[key]
```

---

## 2. OCREngine

### 现状问题

```python
# ocr_backend.py — Protocol 但包含实现代码（误用）
class OCRBackend(Protocol):
    def recognize(self, img, allowlist, ...): ...   # Protocol 方法
    
    # 但直接在 Protocol 里实现了辅助方法
    def recognize_number(self, img, extra_chars): ...
    def recognize_ship(self, img, candidates): ...
```

### 新设计

```python
# autowsgr/vision/ocr.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
from loguru import logger


@dataclass
class OCRResult:
    """OCR 识别结果"""
    text: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None  # (x1, y1, x2, y2)


class OCREngine(ABC):
    """OCR 引擎抽象基类"""
    
    @abstractmethod
    def recognize(
        self,
        image: np.ndarray,
        allowlist: str = "",
    ) -> list[OCRResult]:
        """识别图像中的文字"""
        ...
    
    def recognize_single(
        self,
        image: np.ndarray,
        allowlist: str = "",
    ) -> OCRResult:
        """识别单个文字区域（取置信度最高的）"""
        results = self.recognize(image, allowlist)
        if not results:
            return OCRResult(text="", confidence=0.0)
        return max(results, key=lambda r: r.confidence)
    
    def recognize_number(
        self,
        image: np.ndarray,
        extra_chars: str = "",
    ) -> int | None:
        """识别数字"""
        result = self.recognize_single(image, allowlist="0123456789" + extra_chars)
        text = result.text.strip()
        # 处理 K/M 后缀
        multiplier = 1
        if text.endswith("K"):
            multiplier = 1000
            text = text[:-1]
        elif text.endswith("M"):
            multiplier = 1_000_000
            text = text[:-1]
        try:
            return int(float(text) * multiplier)
        except (ValueError, TypeError):
            return None
    
    def recognize_ship_name(
        self,
        image: np.ndarray,
        candidates: list[str],
    ) -> str | None:
        """识别舰船名称，模糊匹配到候选列表"""
        result = self.recognize_single(image)
        if not result.text:
            return None
        return _fuzzy_match(result.text, candidates)
    
    @classmethod
    def create(cls, engine: str = "easyocr", gpu: bool = False) -> "OCREngine":
        """工厂方法"""
        if engine == "easyocr":
            return EasyOCREngine(gpu=gpu)
        elif engine == "paddleocr":
            return PaddleOCREngine(gpu=gpu)
        else:
            raise ValueError(f"不支持的 OCR 引擎: {engine}")


class EasyOCREngine(OCREngine):
    def __init__(self, gpu: bool = False) -> None:
        import easyocr
        self._reader = easyocr.Reader(["ch_sim", "en"], gpu=gpu)
    
    def recognize(self, image: np.ndarray, allowlist: str = "") -> list[OCRResult]:
        kwargs = {}
        if allowlist:
            kwargs["allowlist"] = allowlist
        raw = self._reader.readtext(image, **kwargs)
        return [
            OCRResult(
                text=text,
                confidence=conf,
                bbox=(int(box[0][0]), int(box[0][1]), int(box[2][0]), int(box[2][1])),
            )
            for box, text, conf in raw
        ]


class PaddleOCREngine(OCREngine):
    def __init__(self, gpu: bool = False) -> None:
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(use_angle_cls=True, lang="ch", use_gpu=gpu, show_log=False)
    
    def recognize(self, image: np.ndarray, allowlist: str = "") -> list[OCRResult]:
        raw = self._ocr.ocr(image, cls=True)
        if not raw or not raw[0]:
            return []
        return [
            OCRResult(
                text=line[1][0],
                confidence=line[1][1],
                bbox=(int(line[0][0][0]), int(line[0][0][1]), int(line[0][2][0]), int(line[0][2][1])),
            )
            for line in raw[0]
        ]


# ── 辅助函数 ──

def _fuzzy_match(text: str, candidates: list[str], threshold: int = 3) -> str | None:
    """基于编辑距离的模糊匹配"""
    best_name = None
    best_dist = threshold + 1
    for name in candidates:
        dist = _edit_distance(text, name)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name if best_dist <= threshold else None


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein 编辑距离"""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = min(
                dp[j] + 1,
                dp[j - 1] + 1,
                prev + (0 if a[i - 1] == b[j - 1] else 1),
            )
            prev = temp
    return dp[n]
```

---

## 3. NativeRecognizer（C++ DLL）

当前的 `api_dll.py` 封装了 C++ 二进制程序做舰型识别和位置识别。保持封装：

```python
# autowsgr/vision/native.py

import subprocess
from pathlib import Path
import numpy as np
from loguru import logger


class NativeRecognizer:
    """C++ 原生识别器（舰船类型、位置等）"""
    
    def __init__(self, bin_path: Path) -> None:
        if not bin_path.exists():
            raise FileNotFoundError(f"原生识别程序不存在: {bin_path}")
        self._bin_path = bin_path
    
    def recognize_enemy(self, images: list[np.ndarray]) -> list[str]:
        """识别敌方舰型"""
        # 调用 C++ 程序
        ...
    
    def recognize_ship_location(self, image: np.ndarray) -> list[tuple[int, int]]:
        """识别舰船位置"""
        ...
```

---

## 模板管理

### 现状问题

```python
IMG = create_namespace(IMG_ROOT, partial(MyTemplate, ...))
# IMG.identify_images['main_page']  ← 运行时动态属性，无类型提示
# IMG.fight_image[3]                ← 魔法数字索引
```

### 新设计

将模板组织为枚举 + 注册表：

```python
# autowsgr/vision/templates.py

from enum import Enum
from pathlib import Path
import cv2
import numpy as np
from loguru import logger

DATA_ROOT = Path(__file__).parent.parent / "data" / "images"


class PageTemplate(Enum):
    """页面识别模板"""
    MAIN_PAGE = "identify_images/main_page.png"
    MAP_PAGE = "identify_images/map_page.png"
    EXERCISE_PAGE = "identify_images/exercise_page.png"
    FIGHT_PREPARE = "identify_images/fight_prepare_page.png"
    EXPEDITION_PAGE = "identify_images/expedition_page.png"
    BATTLE_PAGE = "identify_images/battle_page.png"
    BUILD_PAGE = "identify_images/build_page.png"
    # ... 所有页面


class FightTemplate(Enum):
    """战斗相关模板"""
    SPOT_ENEMY = "fight_image/spot_enemy.png"
    FORMATION_SELECT = "fight_image/formation.png"
    NIGHT_BATTLE = "fight_image/night.png"
    RESULT_MVP = "fight_image/mvp.png"
    # ... 每个都有语义名称


class SymbolTemplate(Enum):
    """通用符号模板"""
    DOCK_FULL = "symbol_image/dock_full.png"
    CONFIRM = "confirm_image/confirm.png"
    CANCEL = "confirm_image/cancel.png"
    GET_SHIP = "symbol_image/get_ship.png"
    # ...


class TemplateRegistry:
    """模板注册表 — 加载和缓存"""
    
    def __init__(self, root: Path = DATA_ROOT) -> None:
        self._root = root
        self._cache: dict[str, np.ndarray] = {}
    
    def get(self, template: PageTemplate | FightTemplate | SymbolTemplate) -> np.ndarray:
        """加载模板图像"""
        key = template.value
        if key not in self._cache:
            path = self._root / key
            img = cv2.imread(str(path))
            if img is None:
                raise FileNotFoundError(f"模板不存在: {path}")
            self._cache[key] = img
            logger.debug("加载模板: {}", key)
        return self._cache[key]
    
    def get_all(self, template_enum: type[Enum]) -> list[np.ndarray]:
        """加载某个枚举下的所有模板"""
        return [self.get(t) for t in template_enum]
```
