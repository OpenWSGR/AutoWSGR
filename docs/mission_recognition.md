# 任务页面识别系统设计规范

> 规范驱动开发: 先完成此文档, 再编写实现代码与测试。

## 1. 目标

为 `MissionPage` 增加**识别当前可见任务列表**的能力, 返回每条任务的名称、
完成状态和进度, 覆盖日常 (第 3 个 tab) 和周常 (第 4 个 tab) 两个子标签。

## 2. 界面布局分析 (960x540 基准)

### 2.1 任务面板结构

```
+------------------------------------------------------------------+
| [<]  地图  建造  强化  [任务]  好友                              |  <- 顶部标签栏 y~0.00-0.10
|------------------------------------------------------------------|
|  [主线] [限定] [日常] [周常] [特殊]                              |  <- 子标签栏 y~0.10-0.16
|------------------------------------------------------------------|
|                                                                  |
|  任务名称 ............ 任务完成度:XX% .... [前往] / [领取]       |  <- 任务行 1
|                                                                  |
|  任务名称 ............ 任务完成度:XX% .... [前往] / [领取]       |  <- 任务行 2
|                                                                  |
|  任务名称 ............ 任务完成度:XX% .... [前往] / [领取]       |  <- 任务行 3
|                                                                  |
|  任务名称 ............ 任务完成度:XX% .... [前往] / [领取]       |  <- 任务行 4
|                                                                  |
+------------------------------------------------------------------+
```

### 2.2 关键坐标 (相对值, 基于 960x540)

| 元素                     | x 范围         | y 范围         | 说明                               |
|--------------------------|----------------|----------------|------------------------------------|
| 子标签 "日常"            | 0.39-0.46      | 0.10-0.16      | 第 3 个子标签                      |
| 子标签 "周常"            | 0.47-0.53      | 0.10-0.16      | 第 4 个子标签                      |
| "前往"/"领取" 按钮中心   | ~0.91          | 各行不同       | 蓝色/金色背景, 用于行定位锚点      |
| 任务名称文本区域         | 0.22-0.60      | 按钮 y+0.07 ~ 按钮 y+0.14 | 按钮下方约0.105处 |
| "任务完成度:XX%" 区域    | 0.75-0.87      | 同任务名称     | 右侧, 低对比度                     |
| 任务列表可滚动区域       | 0.00-1.00      | 0.17-0.95      | 需向下滑动查看更多                 |

### 2.3 "前往" 按钮特征

- 蓝色矩形按钮, 实测 RGB 约 `(30, 138, 239)`, 判定用 `Color(15, 132, 228)` + 容差 40
- 按钮宽度约 0.08, 高度约 0.045
- 未完成任务显示 "前往", 已完成显示 "领取" (金色 ~RGB(252, 220, 37))
- 已领取任务行不显示按钮
- 底部 "一键领取" 按钮更宽 (延伸到 x=0.80), 需过滤

### 2.4 任务完成度

- 格式: `任务完成度:XX%`, 如 `任务完成度:0%`, `任务完成度:60%`, `任务完成度:100%`
- 100% 时按钮变为 "领取"

## 3. 架构设计

### 3.1 模块划分

```
autowsgr/
  data/
    missions.yaml          <- 任务数据库 (已建)
  ui/
    mission_page.py        <- 在现有类中增加识别方法
  vision/
    (现有 OCR/PixelChecker/ImageChecker 不变)
```

### 3.2 数据流

```
截图 (np.ndarray)
  -> 检测 "前往"/"领取" 按钮位置 (蓝色/橙色像素扫描)
    -> 按按钮 y 坐标确定各任务行
      -> 对每行裁切任务名称区域 -> OCR 识别
      -> 对每行裁切完成度区域 -> OCR 识别数字
        -> 模糊匹配数据库 -> 输出 MissionInfo 列表
```

### 3.3 核心数据结构

```python
@dataclass(frozen=True, slots=True)
class MissionInfo:
    """单条任务识别结果。"""
    name: str           # 数据库匹配后的标准名称
    raw_text: str       # OCR 原始文本
    progress: int       # 完成百分比 0-100
    claimable: bool     # 是否可领取 (progress == 100)
    confidence: float   # OCR 置信度
```

## 4. 识别算法

### 4.1 按钮行定位 (锚点扫描)

1. 在 ROI `(0.86, 0.16, 0.96, 0.96)` 内进行**纵向像素扫描**
2. 蓝色判定: `Color.near(Color(15, 132, 228), tolerance=40)` -> "前往"
3. 橙色/金色判定: `r > 180 and g > 120 and b < 80` -> "领取"
4. 对连续匹配色块做纵向聚类 (gap > 5px 视为新行), 取每个簇中心 y 作为行锚点
5. 返回 `list[tuple[float, ButtonType]]` -- (y_center, GOTO/CLAIM)

### 4.2 单行任务识别

对每个行锚点 `(anchor_y)`:

1. **名称 OCR**: 裁切 `ROI(0.22, anchor_y+0.07, 0.60, anchor_y+0.14)` -> OCR
2. **进度 OCR**: 裁切 `ROI(0.75, anchor_y+0.07, 0.87, anchor_y+0.14)` -> OCR 提取数字
3. **数据库匹配**: 对 OCR 文本做模糊匹配 -> 标准任务名

### 4.3 模糊匹配策略

```python
def _match_mission_name(ocr_text: str, candidates: list[str], threshold: int = 5) -> str | None:
    """在任务数据库中模糊匹配任务名。"""
    # 1. 精确匹配
    # 2. 子串包含 (长度比>=70%, 取最长候选)
    # 3. Levenshtein 最短距离 <= threshold
```

### 4.4 滚动策略

单屏可见约 4 条任务, 日常最多约 14 条, 周常最多约 18 条。
需要滚动 3-5 次覆盖全部:

```python
def recognize_all_missions(self, max_scrolls: int = 6) -> list[MissionInfo]:
    """识别当前子标签下所有任务 (含滚动)。"""
    all_missions = []
    seen_names = set()
    for _ in range(max_scrolls):
        screen = self._ctrl.screenshot()
        visible = self._recognize_visible(screen)
        new_count = 0
        for m in visible:
            if m.name not in seen_names:
                seen_names.add(m.name)
                all_missions.append(m)
                new_count += 1
        if new_count == 0:  # 无新任务, 已到底
            break
        self._ctrl.swipe(0.5, 0.7, 0.5, 0.3, duration=0.5)
        time.sleep(0.5)
    return all_missions
```

## 5. 公开 API

在 `MissionPage` 类上新增:

```python
class MissionPage:
    # ... 现有方法 ...

    def recognize_missions(self, screen: np.ndarray) -> list[MissionInfo]:
        """识别截图中可见的任务列表 (单帧, 不滚动)。"""

    def recognize_all_missions(
        self, tab: str = 'daily', max_scrolls: int = 6,
    ) -> list[MissionInfo]:
        """识别指定标签下的全部任务 (含自动滚动)。
        tab: 'daily' 或 'weekly'
        """
```

## 6. 测试计划

### 6.1 文件结构

```
test_pkg/misson_rec/
  tests.py              <- main() -> int
  data.json             <- 每张图期望结果
  images/
    pixel_marker_*.png  <- 7 张截图 (已归档)
```

### 6.2 data.json 格式

```json
{
  "pixel_marker_20260310_123045.png": {
    "missions": [
      {"name": "击退敌军舰队", "progress": 100, "claimable": true},
      {"name": "常规[远征]", "progress": 0, "claimable": false}
    ]
  }
}
```

### 6.3 测试用例

每张截图:
1. 调用 `_find_button_rows()` 检测按钮行数与预期一致
2. 调用 `recognize_missions()` 检测任务名与进度匹配
3. 总体: 任务名匹配率 >= 80% 视为通过 (OCR 容错)

## 7. 已知限制

- [x] "前往" 按钮 RGB 已实测校准: ~(30, 138, 239), "领取" ~(252, 220, 37)
- [ ] OCR 对中文方括号 `[]` 的识别率较好 (实测 0.96+)
- [x] 底部 "一键领取" 宽按钮已通过 x=0.80 宽度检测过滤
- [ ] 进度 "任务完成度:XX%" 文字为浅蓝色在浅灰色背景上, 对比度低, OCR 不稳定
- [ ] 滚动距离需要实测微调, 防止任务行恰好被遮挡
- [ ] 已领取任务行无按钮, 扫描不到锚点 (当前不识别)
