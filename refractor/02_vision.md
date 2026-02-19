# 视觉层 (Vision) — V2 修订版

> **重大变更**: 弃用模板匹配 (Template Matching)，全面采用像素特征检测 (Pixel Feature Detection)。

## 设计转变

### 为什么弃用模板匹配？

| 问题 | 说明 |
|------|------|
| 性能低 | `cv2.matchTemplate` 对每张模板做卷积，多模板场景下延迟高 |
| 维护重 | 需维护 200+ 张模板图片，每次 UI 更新都要重新截图 |
| 鲁棒性差 | 模板匹配对缩放、色差敏感，confidence 阈值难以统一 |
| 依赖 airtest | 旧代码通过 `airtest.core.cv.Template` 封装，引入不必要依赖 |

### 像素特征检测方案

每个页面 / 状态都有若干 **不变的特征像素点**。
只需检查这些像素的颜色是否匹配，即可精准判定页面状态。
坐标一律采用相对値（左上角为 (0,0)，右下角趋近 (1,1)），与截图分辨率无关。

| 优势 | 说明 |
|------|------|
| 极快 | 纯数组索引 + 欧几里得距离，无卷积，单次检测 < 0.01ms |
| 零图片依赖 | 不再需要模板图片文件 |
| 数据化 | 签名可序列化为 YAML/dict，支持热更新和版本管理 |
| 灵活 | 支持 ALL / ANY / COUNT 三种匹配策略 |

## 职责

提供纯粹的图像/文本识别能力，不包含任何游戏逻辑或设备操作。

给定一张图片（numpy 数组），返回识别结果：
- **PixelChecker**: 像素特征检测 → 页面/状态判定
- **OCREngine**: 文字识别 → 文字内容 / 数字

---

## 1. 核心概念

```
Color           一个 BGR 颜色值
    ↓
PixelRule       一条像素规则: 坐标 + 期望颜色 + 容差
    ↓
PixelSignature  像素签名: 多条 PixelRule + 匹配策略 + 名称
    ↓
PixelChecker    检测器: 接收截图 + 签名 → 返回匹配结果
```

---

## 2. API 设计

### 2.1 Color

```python
@dataclass(frozen=True, slots=True)
class Color:
    b: int; g: int; r: int

    @classmethod
    def of(cls, b, g, r) -> Color              # BGR 构造
    @classmethod
    def from_rgb(cls, r, g, b) -> Color         # RGB 构造
    @classmethod
    def from_bgr_tuple(cls, bgr) -> Color       # 元组构造
    @classmethod
    def from_rgb_tuple(cls, rgb) -> Color        # 元组构造

    def distance(self, other: Color) -> float    # 欧几里得距离
    def near(self, other: Color, tolerance=30) -> bool
```

### 2.2 PixelRule

```python
@dataclass(frozen=True, slots=True)
class PixelRule:
    x: float; y: float          # 相对坐标 0.0–1.0，左上角为(0,0)
    color: Color
    tolerance: float = 30.0

    @classmethod
    def of(cls, x, y, bgr, tolerance=30) -> PixelRule      # 便捷构造
    @classmethod
    def from_dict(cls, d: dict) -> PixelRule                # YAML 数据化
    def to_dict(self) -> dict                               # 序列化
```

### 2.3 PixelSignature

```python
class MatchStrategy(Enum):
    ALL = "all"       # 所有规则必须匹配
    ANY = "any"       # 至少一条匹配
    COUNT = "count"   # 匹配数 >= threshold

@dataclass(frozen=True)
class PixelSignature:
    name: str
    rules: tuple[PixelRule, ...]
    strategy: MatchStrategy = MatchStrategy.ALL
    threshold: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> PixelSignature    # YAML 数据化
    def to_dict(self) -> dict
```

### 2.4 PixelChecker（核心检测器）

```python
class PixelChecker:
    """所有方法为 @staticmethod，无状态，接收截图 numpy 数组。
    坐标一律为相对值 (0.0–1.0)，内部自动根据截图分辨率转换。"""

    # 单像素
    def get_pixel(screen, x: float, y: float) -> Color
    def check_pixel(screen, x: float, y: float, color, tolerance=30) -> bool

    # 多像素批量
    def get_pixels(screen, positions: list[tuple[float, float]]) -> list[Color]
    def check_pixels(screen, rules) -> list[bool]

    # 签名匹配
    def check_signature(screen, signature, *, with_details=False) -> PixelMatchResult
    def identify(screen, signatures, *, with_details=False) -> PixelMatchResult | None
    def identify_all(screen, signatures) -> list[PixelMatchResult]

    # 颜色分类
    def classify_color(screen, x: float, y: float, color_map, tolerance=30) -> str | None

    # 图像裁切（坐标同为相对值）
    def crop(screen, x1: float, y1: float, x2: float, y2: float) -> np.ndarray
```

### 2.5 返回值

```python
@dataclass(frozen=True, slots=True)
class PixelDetail:
    rule: PixelRule
    actual: Color
    distance: float
    matched: bool

@dataclass(frozen=True)
class PixelMatchResult:
    matched: bool           # 签名是否匹配
    signature_name: str     # 签名名称
    matched_count: int      # 匹配的规则数
    total_count: int        # 规则总数
    details: tuple[PixelDetail, ...]   # 调试用详情

    def __bool__(self) -> bool: return self.matched
    @property
    def ratio(self) -> float   # 匹配比例
```

---

## 3. 使用示例

### 3.1 页面识别

```python
from autowsgr.vision import Color, PixelRule, PixelSignature, PixelChecker

# 坐标为相对値：左上角 (0,0)，右下角趋近 (1,1)
MAIN_PAGE = PixelSignature(
    name="main_page",
    rules=[
        PixelRule.of(0.073, 0.898, (201, 129, 54)),   # x=70/960, y=485/540
        PixelRule.of(0.036, 0.550, (47, 253, 226)),   # x=35/960, y=297/540
        PixelRule.of(0.917, 0.963, (255, 200, 50)),   # x=880/960, y=520/540
    ],
)

result = PixelChecker.identify(screen, [MAIN_PAGE, MAP_PAGE, ...])
if result:
    print(f"当前页面: {result.signature_name}")
```

### 3.2 状态检测（维修中）

```python
REPAIRING_SLOT_1 = PixelSignature(
    name="repairing_slot_1",
    rules=[
        PixelRule.of(0.076, 0.165, (39, 62, 153)),    # x=73/960, y=89/540
        PixelRule.of(0.073, 0.172, (35, 57, 149)),    # x=70/960, y=93/540
        # ... 10 个特征点
    ],
)

is_repairing = PixelChecker.check_signature(screen, REPAIRING_SLOT_1).matched
```

### 3.3 颜色分类（血量检测）

```python
BLOOD_COLORS = {
    "green":  Color.of(69, 162, 117),    # 绿 = 健康
    "yellow": Color.of(246, 184, 51),    # 黄 = 中破
    "red":    Color.of(230, 58, 89),     # 红 = 大破
    "gray":   Color.of(96, 91, 92),      # 灰 = 击沉
}

# blood_x, blood_y 为相对坐标
status = PixelChecker.classify_color(screen, blood_x, blood_y, BLOOD_COLORS)
```

### 3.4 签名数据化 (YAML)

```yaml
# data/signatures/pages.yaml
# 坐标为相对値：左上角 (0,0)，右下角趋近 (1,1)
- name: main_page
  strategy: all
  rules:
    - {x: 0.073, y: 0.898, color: [201, 129, 54]}
    - {x: 0.036, y: 0.550, color: [47, 253, 226]}
```

```python
import yaml
with open("data/signatures/pages.yaml") as f:
    data = yaml.safe_load(f)
signatures = [PixelSignature.from_dict(d) for d in data]
```

---

## 4. OCR 引擎

OCR 部分保持 ABC + 双后端设计。

```python
class OCREngine(ABC):
    def recognize(image, allowlist="") -> list[OCRResult]
    def recognize_single(image, allowlist="") -> OCRResult
    def recognize_number(image, extra_chars="") -> int | None
    def recognize_ship_name(image, candidates, threshold=3) -> str | None

    @classmethod
    def create(engine="easyocr", gpu=False) -> OCREngine
```

---

## 5. 已移除的组件

| 组件 | 原文件 | 说明 |
|------|--------|------|
| `ImageMatcher` | vision/matcher.py | 模板匹配类 → 被 `PixelChecker` 取代 |
| `MatchResult` | vision/matcher.py | 模板匹配结果 → 被 `PixelMatchResult` 取代 |
| `TemplateRegistry` | vision/templates.py | 模板注册表 → 不再需要模板文件 |
| `PageTemplate` 枚举 | vision/templates.py | 改用 `PixelSignature` 数据化 |
| `FightTemplate` 枚举 | vision/templates.py | 同上 |
| `SymbolTemplate` 枚举 | vision/templates.py | 同上 |
| `NativeRecognizer` | vision/native.py | C++ DLL → 保留但延后实现 |
| `load_template()` | vision/matcher.py | 不再需要 |
| `match()` / `match_any()` / `match_best()` | vision/matcher.py | cv2.matchTemplate 封装 → 已移除 |
| `locate_image_center()` | utils/api_image.py | 旧模板匹配 → 已移除 |
| `MyTemplate` / `IMG` | constants/image_templates.py | airtest Template 封装 → 已移除 |

---

## 6. 文件结构

```
autowsgr/vision/
├── __init__.py          # 公开 API re-export
├── matcher.py           # Color, PixelRule, PixelSignature, PixelChecker
└── ocr.py               # OCREngine ABC, EasyOCR, PaddleOCR
```

模板图片目录 (`data/images/`) 将逐步迁移为 `PixelSignature` YAML 数据文件。
