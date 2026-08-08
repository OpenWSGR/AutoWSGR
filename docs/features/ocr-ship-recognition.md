# 舰船识别 OCR 测试记录

本文记录 FastOCR 引擎、准备页和船池舰船信息识别改造的离线基准与自动测试方法。
整理日期：2026-08-08。

## 1. 测试范围

测试覆盖：

- 准备页六个槽位的等级和舰种；
- ADB 无损截图与 scrcpy H264 截图；
- FastOCR、RapidOCR、EasyOCR 和 LuLing-OCR 对照；
- 原图与逐 ROI Otsu 二值图；
- 船池舰名、舰种、等级的卡片坐标绑定；
- 同名候选卡片的舰种和等级约束校验；
- 增强 OCR 开关关闭时的 EasyOCR 兼容路径。

本记录不覆盖换船状态机、多级快照、`relaxed` API 或其他分辨率。

## 2. 环境与方法

| 项目 | 配置 |
|---|---|
| 游戏分辨率 | 1280x720 |
| 截图源 | ADB 无损截图、scrcpy H264 截图 |
| FastOCR | MaaFramework FastOCR，CPU 执行器 |
| FastOCR 参数 | `only_rec=False`、`threshold=0.3` |
| RapidOCR | 3.9.2，PP-OCRv6-small recognition-only |
| EasyOCR | 默认参数、船只小字优化参数 |
| 重复轮次 | 3 轮 |
| 二值化 | 每张 ROI 独立执行 Otsu |

相同截图重复三轮时，错误输出均固定复现，没有观察到随机变化。

## 3. 等级 OCR

### 3.1 校准区域

测试和生产代码使用同一组 `SHIP_LEVEL_CROP` 坐标：

```python
{
    0: (0.0508, 0.5667, 0.0953, 0.5875),
    1: (0.1672, 0.5667, 0.2117, 0.5875),
    2: (0.2836, 0.5667, 0.3281, 0.5875),
    3: (0.3992, 0.5667, 0.4438, 0.5875),
    4: (0.5164, 0.5667, 0.5609, 0.5875),
    5: (0.6328, 0.5667, 0.6773, 0.5875),
}
```

真实等级：

- 第 1 队：`1、103、101、3、5、5`；
- 第 2 至 4 队：全部为 `110`。

样本覆盖个位数、三位数和游戏等级上限。每种模型、每种预处理的统计口径为：

```text
4 支舰队 x 2 种截图源 x 6 个槽位 x 3 轮 = 144 次
```

### 3.2 2592 次识别汇总

下表记录错误次数：

| 模型 | 原图错误 | Otsu 错误 | 合计错误 |
|---|---:|---:|---:|
| PP-OCRv5 mobile + FastOCR | 27/144 | 0/144 | 27/288 |
| PP-OCRv5 server + FastOCR | 0/144 | 0/144 | 0/288 |
| PP-OCRv6 tiny + FastOCR | 6/144 | 6/144 | 12/288 |
| **PP-OCRv6 small + FastOCR** | **0/144** | **0/144** | **0/288** |
| PP-OCRv6 medium + FastOCR | 0/144 | 30/144 | 30/288 |
| PP-OCRv6 small + RapidOCR | 6/144 | 0/144 | 6/288 |
| LuLing-OCR | 90/144 | 72/144 | 162/288 |
| EasyOCR 默认参数 | 75/144 | 12/144 | 87/288 |
| EasyOCR 优化参数 | 6/144 | 0/144 | 6/288 |

总计 2592 次识别，出现 330 次错误。关键观察：

1. PP-OCRv6-small + FastOCR 在原图和 Otsu 输入上均为 144/144；
2. RapidOCR 的 6 次原图错误均为第 1 队第 1 槽 `Lv.1` 固定误读为 `Lv.11`；
3. PP-OCRv6-medium 在原图无错误，但 Otsu 增加 30 次错误；
4. Otsu 对不同模型的影响不一致，不能作为通用增益；
5. PP-OCRv6-small + FastOCR 原图平均 6.84ms，P95 为 7.13ms；
6. EasyOCR 优化参数的 Otsu 输入平均 31.06ms，P95 为 33.67ms。

生产链路因此采用 PP-OCRv6-small + FastOCR + 校准后的原图 ROI。

## 4. 舰种 OCR

### 4.1 校准区域与真值

测试和生产代码使用同一组 `SHIP_TYPE_CROP` 坐标：

```python
{
    0: (0.050825, 0.5278, 0.086725, 0.5681),
    1: (0.167225, 0.5278, 0.203125, 0.5681),
    2: (0.283625, 0.5278, 0.319625, 0.5681),
    3: (0.400025, 0.5278, 0.436025, 0.5681),
    4: (0.516425, 0.5278, 0.552425, 0.5681),
    5: (0.633625, 0.5278, 0.669625, 0.5681),
}
```

四支舰队真值：

| 舰队 | 六个槽位 |
|---|---|
| 1 | 航母、轻母、装母、战列、航战、战巡 |
| 2 | 重巡、航巡、雷巡、轻巡、重炮、驱逐 |
| 3 | 导潜、潜艇、炮潜、补给、导驱、防驱 |
| 4 | 导巡、防巡、大巡、导战、空、空 |

共 22 个有舰槽和 2 个空槽。输入分为：

- 原图：ROI 使用 `INTER_LINEAR` 放大 4 倍；
- 二值图：ROI 执行 Otsu 后使用 `INTER_LINEAR` 放大 4 倍。

### 4.2 静态截图三轮

每个截图源包含 66 个有舰槽样本：

| OCR | 截图源 | 输入 | 有舰槽正确 | 平均耗时/槽 |
|---|---|---|---:|---:|
| EasyOCR 默认 | ADB / scrcpy | 原图 | 66/66、66/66 | 34.76 / 33.51ms |
| EasyOCR 默认 | ADB / scrcpy | Otsu | 63/66、63/66 | 34.22 / 33.95ms |
| EasyOCR 优化 | ADB / scrcpy | 原图 | 66/66、66/66 | 13.89 / 13.65ms |
| EasyOCR 优化 | ADB / scrcpy | Otsu | 63/66、60/66 | 13.99 / 13.70ms |
| FastOCR | ADB / scrcpy | 原图 | 66/66、66/66 | 13.08 / 10.49ms |
| FastOCR | ADB / scrcpy | Otsu | 60/66、60/66 | 11.64 / 11.60ms |

### 4.3 实机切换三轮

实机按固定顺序切换 120 次舰队，同时采集 ADB 和 scrcpy 截图。两个截图源均正确识别
目标舰队 120/120。每种引擎、每个截图源包含 660 个有舰槽和 60 个空槽。

| OCR | 截图源 | 输入 | 有舰槽正确 | 空槽正确 | 全部槽位 |
|---|---|---|---:|---:|---:|
| EasyOCR 默认 | ADB / scrcpy | 原图 | 660/660、660/660 | 60/60、60/60 | 720/720、720/720 |
| EasyOCR 默认 | ADB / scrcpy | Otsu | 630/660、630/660 | 60/60、60/60 | 690/720、690/720 |
| EasyOCR 优化 | ADB / scrcpy | 原图 | 660/660、660/660 | 60/60、60/60 | 720/720、720/720 |
| EasyOCR 优化 | ADB / scrcpy | Otsu | 630/660、603/660 | 60/60、60/60 | 690/720、663/720 |
| FastOCR | ADB / scrcpy | 原图 | 660/660、660/660 | 60/60、60/60 | 720/720、720/720 |
| FastOCR | ADB / scrcpy | Otsu | 600/660、600/660 | 60/60、60/60 | 660/720、660/720 |

静态与实机结果合并后：

- FastOCR X4 原图：1320/1320；
- FastOCR X4 Otsu：1200/1320；
- EasyOCR 优化 X4 原图：1320/1320；
- EasyOCR 默认 X4 原图：1320/1320；
- 所有方案对空槽均无舰种误报。

FastOCR 原图平均 10.47ms/槽，EasyOCR 优化原图平均 14.57ms/槽，EasyOCR 默认原图
平均 34.63ms/槽。生产链路使用 X4 原图，不执行 Otsu。

## 5. 卡片绑定与候选校验

自动测试使用构造截图和 OCR mock 验证以下行为：

1. 舰名坐标可恢复到原始截图坐标；
2. 同一卡片的 `card_x` 和 `row_key` 用于裁剪等级；
3. 舰种按舰名中心和卡片行坐标裁剪；
4. 舰种按 2、3、4 倍顺序尝试，并在首次有效结果后停止；
5. 等级执行共享纠错、1 至 110 范围校验和有限重试；
6. 同名候选逐卡校验，首张不符合舰种或等级时继续检查下一张；
7. 没有符合约束的候选时不执行点击。

涉及的测试文件：

- `testing/vision/test_ocr.py`
- `testing/ops/test_launcher_unit.py`
- `testing/ui/battle_preparation/test_unit.py`
- `testing/ui/test_choose_ship_page.py`
- `testing/ui/test_ship_list.py`

## 6. 模型资源校验

| 文件 | 字节数 | SHA256 |
|---|---:|---|
| `det.onnx` | 9,893,172 | `66c0f34caaf432553710fd9973a7134d8cf924db7109310c3d2562dcc39b209d` |
| `rec.onnx` | 21,146,753 | `7dcf6298d77d2a6eb44c1ebeed990826ca895a9c68d955a3eace00763d052949` |
| `keys.txt` | 74,947 | `b5f2bfe2bdd9448429e3e82b51c789775d9b42f2403d082b00662eb77e401c5d` |

合计 31,114,872 字节。模型来源和 MIT 许可证记录在
`autowsgr/data/ocr/ppocr_v6_small/README.md` 与 `LICENSE`。

## 7. 自动验证命令

聚焦测试：

```powershell
uv run pytest -q `
  testing/vision/test_ocr.py `
  testing/ops/test_launcher_unit.py `
  testing/ui/battle_preparation/test_unit.py `
  testing/ui/test_choose_ship_page.py `
  testing/ui/test_ship_list.py
```

完整验证：

```powershell
uv run pytest -q
uv run pre-commit run --all-files
git diff --check upstream/main...HEAD
```

2026-08-08 最终分支执行结果：

| 检查 | 结果 |
|---|---|
| 上述 5 个 OCR 聚焦测试文件 | 244 passed |
| 全量 `uv run pytest -q` | 815 passed |
| PR 全部变更文件的 pre-commit | 全部 hooks 通过 |
| `git diff --check` | 通过 |

Windows 工作树中的 `.claude/skills` 和 `CLAUDE.md` 是符号链接。全仓 pre-commit 的
`end-of-file-fixer` 会把它们当普通指针文件并错误添加换行，因此全仓执行后恢复了这两个
文件，再对本 PR 的全部变更文件运行相同 hooks；Ruff、格式化、codespell、大文件检查及
其他 hooks 均通过。这两个符号链接未包含在本 PR 差异中。

## 8. 结论与限制

1. 在现有 1280x720 样本中，PP-OCRv6-small + FastOCR 的等级原图识别为 144/144；
2. 舰种 X4 原图识别为 1320/1320，Otsu 会降低准确率；
3. 卡片坐标绑定消除了按 OCR 返回顺序组合属性的风险；
4. 增强开关默认关闭，保留 EasyOCR 回退路径；
5. 实机截图未提交到仓库，以上基准是本次调研记录，不作为跨分辨率准确率承诺；
6. 其他分辨率、界面主题或未采集舰种需要单独校准和回归。
