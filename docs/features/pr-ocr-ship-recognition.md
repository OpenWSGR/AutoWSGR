# FastOCR 舰船识别调研与方案说明

本文说明本次 PR 为什么引入 FastOCR，以及舰名、舰种和等级识别可靠性改造的依据。
详细测试数据见
[`docs/features/ocr-ship-recognition.md`](ocr-ship-recognition.md)。

## 1. 结论

本次 PR 采用以下方案：

1. 增加基于 MaaFramework FastOCR 的可选船只 OCR 引擎；
2. 使用 PP-OCRv6-small 检测、识别模型及字典，资源合计 31,114,872 字节；
3. `enhanced_ship_ocr` 默认关闭，关闭时继续使用现有 EasyOCR 链路；
4. 准备页等级和舰种使用针对 1280x720 校准的固定区域；
5. 船池中的舰名、舰种和等级按同一张卡片坐标绑定；
6. 候选舰船逐卡读取约束信息，避免按 OCR 返回行号或顺序拼接属性。

FastOCR 并非在所有 OCR 场景中替换 EasyOCR。它只在用户主动开启增强船只识别后，
用于舰船相关识别节点。

## 2. 问题背景

原链路在小字号舰船信息上主要存在三类问题：

- 准备页等级区域包含过多空白或相邻元素，可能把 `Lv.1` 识别为 `Lv.11`；
- 船池舰种、等级与舰名按返回顺序组合，同一行有多个候选时可能发生属性错位；
- 识别到同名候选后缺少卡片级约束校验，可能点击舰种或等级不符合规则的卡片。

这些问题不能只依靠更换 OCR 模型解决。模型、裁剪区域、输入预处理和识别结果的坐标
绑定必须一起验证。

## 3. 方案调研

### 3.1 候选方案

本次实测覆盖：

- MaaFramework FastOCR：PP-OCRv5 mobile/server、PP-OCRv6 tiny/small/medium；
- RapidOCR 3.9.2：PP-OCRv6-small recognition-only；
- EasyOCR：默认参数和船只小字优化参数；
- LuLing-OCR：原始 PyTorch 模型；
- 原图与逐 ROI Otsu 二值化两种输入。

测试同时使用 ADB 无损截图和 scrcpy H264 截图，所有组合重复三轮。测试重点不是判断
某个引擎的通用能力，而是确定它在战舰少女 R 1280x720 舰船小字场景中的表现。

### 3.2 等级识别结果

每种输入的统计口径为：

```text
4 支舰队 x 2 种截图源 x 6 个槽位 x 3 轮 = 144 次
```

关键结果如下：

| 方案 | 非二值化 | Otsu | 主要结论 |
|---|---:|---:|---|
| FastOCR + PP-OCRv6-small | 144/144 | 144/144 | 两种输入均无错误 |
| RapidOCR + PP-OCRv6-small | 138/144 | 144/144 | 原图固定误读 `Lv.1` |
| EasyOCR 优化参数 | 138/144 | 144/144 | 二值图准确，但耗时更高 |
| EasyOCR 默认参数 | 69/144 | 132/144 | 小字场景错误较多 |
| LuLing-OCR | 54/144 | 72/144 | 字符混淆较多 |

FastOCR + PP-OCRv6-small 在非二值化输入下平均耗时 6.84ms，P95 为 7.13ms。
EasyOCR 优化参数在二值图上平均耗时 31.06ms，约为前者的 4.5 倍。

因此等级生产链路选择 FastOCR、校准后的原图 ROI，不增加 Otsu 预处理。

### 3.3 舰种识别结果

舰种测试使用校准后的 ROI，并比较 X4 原图与 X4 Otsu 输入。静态截图和 120 次实机
舰队切换合计得到每种引擎 1320 个双源有舰槽样本。

| 方案 | X4 原图 | X4 Otsu | 平均耗时/槽 |
|---|---:|---:|---:|
| FastOCR | 1320/1320 | 1200/1320 | 10.47ms |
| EasyOCR 优化参数 | 1320/1320 | 1233/1320 | 14.57ms |
| EasyOCR 默认参数 | 1320/1320 | 1260/1320 | 34.63ms |

三种引擎在 X4 原图上均无错误，但 FastOCR 平均耗时最低。Otsu 对舰种文字造成稳定
负向影响，因此舰种生产链路使用 X4 原图。

## 4. 工程实现

### 4.1 引擎与模型

`FastOCREngine` 通过 MaaFramework FastOCR 加载内置模型，使用 CPU 执行器，主要参数为：

```python
only_rec=False
threshold=0.3
```

模型放在 `autowsgr/data/ocr/ppocr_v6_small/`，随包分发，首次运行不需要联网下载。
模型来自 MaaXYZ/MaaCommonAssets，对应 MIT 许可证随资源一并提交。

### 4.2 兼容与回退

配置项如下：

```yaml
ocr:
  enhanced_ship_ocr: false
```

- `false`：不创建 FastOCR 实例，保持现有 EasyOCR 行为；
- `true`：船只相关节点优先使用 FastOCR；
- FastOCR 不替换章节、阵型等其他 OCR 节点。

### 4.3 区域校准与统一解析

- 准备页六个等级和舰种区域使用固定的 1280x720 归一化坐标；
- 船池等级裁剪偏移为 `(-62, -38, -2, -20)`；
- 船池舰种裁剪偏移为 `(-62, -59, -13, -34.5)`；
- 船池小字按 2、3、4 倍逐级尝试；
- 等级共享字符纠错和 1 至 110 范围校验；
- 舰种共享允许字符集合和标准化规则。

### 4.4 卡片坐标绑定

船池识别先记录舰名中心坐标与卡片行标识，再从同一卡片读取等级和舰种。候选卡片
逐张校验，只有名称命中且已声明约束符合时才进入点击流程。这样可避免以下错误：

- 同一行两张卡片的舰名和等级交叉组合；
- OCR 返回顺序变化导致舰种绑定到另一张卡片；
- 第一个同名候选不符合等级或舰种时仍被直接点击。

## 5. 风险与边界

- 当前坐标只针对 1280x720 界面完成实测，其他分辨率需要重新校准；
- 测试覆盖已采集的舰种和等级样本，不代表未出现字体状态的绝对正确率；
- 模型资源增加约 31.1MB 包体积；
- 增强开关默认关闭，可在出现兼容问题时直接回退到原 EasyOCR 链路；
- 实机截图样本未随 PR 提交，防止仓库体积继续增长；核心路由、坐标、解析和卡片绑定
  行为由单元测试覆盖。

## 6. 本 PR 范围

本 PR 包含：

- FastOCR 引擎、PP-OCRv6-small 模型和依赖；
- 增强 OCR 配置与启动器接线；
- 准备页和船池等级、舰种区域校准；
- 船池卡片坐标绑定与候选卡片校验；
- 对应单元测试和本调研、测试记录。

本 PR 不包含换船状态机重构、准备页多级快照、`relaxed` API、舰船库同步和 OCR 样本
采集工具。

## 7. 参考

- MaaCommonAssets PP-OCRv6-small：
  <https://github.com/MaaXYZ/MaaCommonAssets/tree/main/OCR/ppocr_v6/small>
- MaaFramework：<https://github.com/MaaXYZ/MaaFramework>
- 详细测试记录：
  [`docs/features/ocr-ship-recognition.md`](ocr-ship-recognition.md)
