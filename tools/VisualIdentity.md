# 视觉识别系统指南

AutoWSGR 使用两种主要方式来识别游戏状态和界面元素：**图像模板匹配 (Image Matching)** 和 **像素特征签名 (Pixel Signature)**。

本文档详细介绍了这两种机制及其使用场景，特别是如何定义和调试 `PixelRules`。

## 1. 像素特征签名 (PixelSignature)

像素签名是通过检查屏幕上特定位置的像素颜色来识别页面的方法。相比图像匹配，它通常更快且对背景变化更具鲁棒性（前提是选取的特征点是固定的）。

### 核心组件

#### `PixelRule`
定义单个像素点的检查规则。

```python
from autowsgr.vision import PixelRule

# 定义规则: 在相对坐标 (0.5, 0.5) 处，颜色应接近 (255, 255, 255)，容差为 30
rule = PixelRule.of(
    x=0.5,          # 相对横坐标 (0.0 - 1.0)
    y=0.5,          # 相对纵坐标 (0.0 - 1.0)
    color=(255, 255, 255), # 目标 RGB 颜色
    tolerance=30.0  # 欧氏距离容差
)
```

#### `PixelSignature`
由一组 `PixelRule` 组成的集合，用于描述一个完整的界面状态。

```python
from autowsgr.vision import PixelSignature, MatchStrategy

signature = PixelSignature(
    name="main_page_menu",
    strategy=MatchStrategy.ALL,  # 策略: ALL (全匹配) 或 ANY (任意匹配)
    rules=[
        PixelRule.of(0.94, 0.20, (227, 227, 227), tolerance=30.0),
        PixelRule.of(0.50, 0.56, (24, 101, 181), tolerance=30.0),
    ]
)
```

#### `CompositePixelSignature`
组合多个 `PixelSignature`，通常用于处理同一页面的不同变体（如活动页面的不同背景）。

```python
from autowsgr.vision import CompositePixelSignature

composite = CompositePixelSignature.any_of(
    "event_page_variants",
    signature_variant_a,
    signature_variant_b
)
```

### 使用方法

```python
from autowsgr.vision import PixelChecker

# 检查当前屏幕是否匹配签名
is_match = PixelChecker.check_signature(screen_image, signature).matched
```

### 调试与生成

使用 `tools/debug_screenshot.py` 可以方便地获取坐标和颜色：

```bash
# 获取鼠标位置的相对坐标和颜色
python tools/debug_screenshot.py --pixel 0.5,0.5
```

## 2. 图像模板匹配 (Image Matching)

基于 OpenCV 的模板匹配，适用于图标、按钮等具有丰富纹理特征的元素。

### 核心组件

#### `TemplateKey`
在 `autowsgr/image_resources/keys.py` 中定义的枚举，映射到具体的资源文件。

#### `ImageChecker`
执行匹配的工具类。

```python
from autowsgr.vision import ImageChecker
from autowsgr.image_resources import TemplateKey

# 查找模板，返回匹配结果对象 (包含坐标、置信度等) 或 None
result = ImageChecker.find_template(
    screen_image,
    TemplateKey.SOME_BUTTON,
    confidence=0.8
)
```

## 3. 选择建议

| 场景 | 推荐方式 | 原因 |
| :--- | :--- | :--- |
| **全屏状态识别** | **PixelSignature** | 速度快，不受背景动画干扰 (只要选取固定 UI 锚点) |
| **按钮/图标定位** | **Image Matching** | 需要获取点击坐标，且图标位置可能不固定 |
| **动态背景页面** | **PixelSignature** | 避开背景区域，只检测固定 UI 元素颜色 |
| **复杂纹理/文字** | **Image Matching** | 颜色单一但形状复杂，像素点难以描述 |

## 4. 常见问题排查

### 像素验证失败
日志示例: `[船位检测] 黄色簇检测到但像素验证失败: (0.522, 0.357)`

**原因**:
1. **坐标偏移**: 分辨率缩放或模拟器渲染差异导致取色点偏离。
2. **颜色渲染差异**: 不同渲染模式 (DirectX/OpenGL) 下颜色值有细微差别。
3. **动态效果**: 选取的点上有光效或透明度变化。

**解决**:
1. 增大 `tolerance` (如从 10 增加到 30)。
2. 选取更稳定的特征点 (纯色、无透明度、无动画)。
3. 使用 `tools/debug_screenshot.py` 重新校准坐标和颜色。
