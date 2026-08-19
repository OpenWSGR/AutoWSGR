# 视觉识别系统

> 返回 [架构概述](README.md)

本文档描述 AutoWSGR 的三层视觉识别栈及图像资源管理。

---

## 三层视觉栈

```
┌─────────────────────────────────────────┐
│  Layer 3: OCR                           │  文字识别 (舰船名/数字/阵型)
│    OCREngine → EasyOCREngine            │
├─────────────────────────────────────────┤
│  Layer 2: 模板匹配                       │  图片模板搜索 (按钮/图标)
│    ImageChecker + ImageTemplate         │
├─────────────────────────────────────────┤
│  Layer 1: 像素特征                       │  固定像素点颜色检测 (页面/状态)
│    PixelChecker + PixelSignature        │
└─────────────────────────────────────────┘
```

三层可独立使用，也可组合（如战斗识别器同时用模板匹配 + 像素特征作为双通道确认）。

---

## Layer 1: 像素特征

**文件**: `autowsgr/vision/pixel.py`（数据模型），`autowsgr/vision/matcher.py`（检测引擎）

通过检测截图中固定位置的像素颜色来判断页面/状态。速度极快（无需图像搜索），适用于页面识别。

### 数据模型

```python
Color(r, g, b)                    # RGB 颜色值
  .distance(other) -> float       # 欧几里得色彩距离
  .near(other, tolerance) -> bool # 是否在容差内

PixelRule(x, y, color, tolerance) # 单像素检测规则
  # x, y: 相对坐标 (0.0 ~ 1.0)
  # color: 期望 RGB 颜色
  # tolerance: 最大色彩距离 (默认 30.0)

MatchStrategy                     # 多规则匹配策略
  ALL   — 所有规则必须匹配
  ANY   — 至少一条规则匹配
  COUNT — 匹配数量 >= threshold

PixelSignature(name, rules, strategy, threshold)
  # 多条 PixelRule 组合定义一个页面/状态

CompositePixelSignature
  # 多个 PixelSignature 的 OR 组合
  .any_of(name, *signatures) -> CompositePixelSignature
```

### 检测引擎

```python
class PixelChecker:
    @staticmethod
    def check_rule(screen, rule) -> PixelDetail
    @staticmethod
    def is_matching(screen, signature) -> bool
    @staticmethod
    def check_signature(screen, signature) -> PixelMatchResult
```

### 使用示例

```python
# 定义主页面签名
MAIN_PAGE_SIG = PixelSignature(
    name='main_page',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.50, 0.85, (201, 129, 54)),
        PixelRule.of(0.75, 0.90, (34, 112, 195)),
    ],
)

# 检测
screen = ctrl.screenshot()
if PixelChecker.is_matching(screen, MAIN_PAGE_SIG):
    print('当前在主页面')
```

---

## Layer 2: 模板匹配

**文件**: `autowsgr/vision/image_matcher.py`（引擎），`autowsgr/vision/image_template.py`（数据模型），`autowsgr/vision/roi.py`（ROI）

通过 OpenCV 模板匹配在截图中搜索目标图片。适用于按钮检测、图标识别等。

### 数据模型

```python
ROI(x1, y1, x2, y2)              # 感兴趣区域 (相对坐标 0-1)
  .crop(screen) -> np.ndarray    # 裁剪截图 (返回视图, 非拷贝)
  .to_absolute(w, h)             # 转绝对像素坐标
  .contains(x, y)                # 判断点是否在区域内

ImageTemplate(
    image: np.ndarray,            # 模板图片 (HxWx3, RGB)
    name: str,                    # 模板名称
    source_resolution: (960, 540) # 采集分辨率
)

ImageRule(templates, strategy, unmask_factor=0.0)  # 多模板 + 匹配策略
  # unmask_factor: 截图搜索区域反蒙版还原因子 (见“反蒙版还原”小节)
ImageSignature(rules, strategy)   # 多规则组合签名

ImageMatchDetail(found, confidence, location, template_name)
ImageMatchResult(matched, details)
```

### ImageChecker 引擎

```python
class ImageChecker:
    @staticmethod
    def _scale_template_if_needed(template_img, screen_w, screen_h, source_resolution)
        # 截图分辨率不同时自动缩放模板

    @staticmethod
    def _unmask(img, factor)
        # 反蒙版还原: img / factor → clip(0,255); factor<=0 透传

    @staticmethod
    def _match_single_template(screen, template, roi, confidence, method, unmask_factor=0.0)
        # 单模板匹配 → ImageMatchDetail | None
        # unmask_factor>0 时对截图搜索区域 (非模板) 做 _unmask 后再匹配

    @staticmethod
    def fetch_all_templates(screen, signature, roi) -> list[ImageMatchDetail]
    def is_matching(screen, signature, roi) -> bool
    def find_match(screen, signature, roi) -> ImageMatchDetail | None

    # 便捷方法均接受 unmask_factor 关键字 (默认 0.0):
    # find_template / find_any / find_best / find_all / template_exists / find_all_occurrences
```

### 分辨率适配

模板图片采集基准为 `960x540`。当实际截图分辨率不同时，`ImageChecker` 自动按比例缩放模板：

- 缩小: `cv2.INTER_AREA`（抗锯齿）
- 放大: `cv2.INTER_LINEAR`

### 反蒙版还原 (unmask)

`_unmask(img, factor)` 把被半透明黑罩压暗的画面除以 `factor` 还原亮度（借鉴 WSG-NCC 的 `unmask=0.33`）。通过 `ImageRule.unmask_factor` 字段或各 `find_*` 方法的 `unmask_factor` 参数启用，默认 `0.0`（禁用，完全向后兼容）。

- **作用范围**：仅还原截图搜索区域，**模板保持原始亮度**（模板是干净基准）。

> ⚠️ **TM_CCOEFF_NORMED 缩放不变性**：相关系数在正标量乘法下不变，故纯乘性均匀压暗本就不破坏模板匹配置信度（实测压暗屏幕置信度仍 ~0.998），**unmask 对模板匹配几乎无意义**。其价值在于像素级 MAE 对比（如“操作驱动状态追踪”中对比 click 前后边缘像素），以及未来含加性偏移的场景。

---

## Layer 3: OCR 文字识别

**文件**: `autowsgr/vision/ocr.py`

### 抽象基类

```python
class OCREngine(ABC):
    @abstractmethod
    def recognize(image, allowlist='') -> list[OCRResult]

    # 高层便捷方法 (基于 recognize 构建):
    def recognize_single(image, allowlist) -> OCRResult | None
    def recognize_number(image) -> int | None
    def recognize_ship_name(image, candidates) -> str | None
```

### EasyOCREngine

```python
class EasyOCREngine(OCREngine):
    @classmethod
    def create(cls, gpu=False) -> EasyOCREngine
    # 内部使用 easyocr 库
```

### OCRResult

```python
@dataclass
class OCRResult:
    text: str                              # 识别文本
    confidence: float                      # 置信度 (0.0-1.0)
    bbox: tuple[int, int, int, int] | None # 边界框 (x1, y1, x2, y2)
```

### 舰船名模糊匹配

`recognize_ship_name()` 使用 Levenshtein 编辑距离在 `SHIPNAMES` 数据库中查找最接近的候选：

- 编辑距离 <= 阈值 → 返回候选名
- 编辑距离 > 阈值 → 抛出 `ShipNameMismatchError`

全局替换规则 `REPLACE_RULE` 处理常见 OCR 错误（如 `'鲍鱼' → '鲃鱼'`）。

---

## 图像资源管理

**文件**: `autowsgr/image_resources/`

### TemplateKey 枚举

**文件**: `autowsgr/image_resources/keys.py`

所有图像模板的标识键，按功能分组：

| 分组     | 示例                                         |
|----------|----------------------------------------------|
| 战斗     | PROCEED, DOCK_FULL, FORMATION, FIGHT_PERIOD, RESULT, GET_SHIP, ... |
| 结果等级 | RESULT_GRADE_S, RESULT_GRADE_A, ..., RESULT_GRADE_SS |
| 操作     | COOK_BUTTON, BUILD_BUTTON, INTENSIFY_BUTTON, ... |
| 通用     | REPAIR_BUTTON, SUPPLY_BUTTON, ...            |

### CombatTemplates

**文件**: `autowsgr/image_resources/combat.py`

战斗相关模板的静态访问器：

```python
CombatTemplates.FORMATION  → ImageTemplate
CombatTemplates.RESULT     → ImageTemplate
```

### Templates

**文件**: `autowsgr/image_resources/ops.py`

操作类模板的层级访问器：

```python
Templates.Cook.COOK_BUTTON → ImageTemplate
Templates.Build.BUILD_BUTTON → ImageTemplate
```

### LazyTemplate 懒加载

**文件**: `autowsgr/image_resources/_lazy.py`

模板图片在首次访问时从 `data/images/` 目录加载。使用 `LazyTemplate` 描述符，避免启动时一次性加载所有图片：

```python
class LazyTemplate:
    def __get__(self, obj, type) -> ImageTemplate:
        # 首次访问: 从磁盘读取图片 → 转 RGB → 缓存
        # 后续访问: 直接返回缓存
```

图片存储在 `data/images/` 的子目录中：

```
data/images/
├── combat/       # 战斗状态模板
├── build/        # 建造页面
├── choose_ship/  # 选船页面
├── cook/         # 食堂
├── decisive/     # 决战
├── event/        # 活动
├── reward/       # 奖励
├── ui/           # 通用 UI 元素
└── common/       # 公共模板
```

---

## 开发工具

### pixel_marker.py

**文件**: `tools/pixel_marker.py`

tkinter GUI 工具，用于在真实截图上标注 `PixelSignature`：

- **左键**: 添加像素点 → 自动读取 RGB 颜色 + 归一化坐标
- **右键**: 删除标注点
- **Ctrl+S**: 导出为 YAML 格式
- **Ctrl+C**: 复制为 Python 代码
- **F5**: 重新截图

```bash
python tools/pixel_marker.py --serial 127.0.0.1:5555
```

### debug_screenshot.py

**文件**: `tools/debug_screenshot.py`

截图调试工具，支持 ROI 裁剪 + OCR 测试：

```bash
# 截图并在指定 ROI 区域执行 OCR
python tools/debug_screenshot.py --roi 0.8,0.8,0.9,0.9 --allowlist "0-9"
```

---

## 与其他模块的关系

- **上游**: [emulator](emulator.md) 提供 `screenshot()` 截图
- **下游 (页面识别)**: [ui](ui.md) 的页面注册中心使用 `PixelChecker` 检测当前页面
- **下游 (战斗识别)**: [combat-engine](combat-engine.md) 的 `CombatRecognizer` 使用全部三层视觉能力
- **下游 (操作层)**: [ops](ops.md) 使用 `ImageChecker` 检测按钮、使用 OCR 读取数值
