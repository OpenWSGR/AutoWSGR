# 主流手游自动化脚本 OCR / 图像识别方案调研

> 调研目的：解决 AutoWSGR「编队页等级/舰种 OCR 识别不到」问题，参考主流开源自动化项目的成熟方案。
> 调研日期：2026-08-06。来源：mirrorchyan 镜像站项目列表 + 各项目 GitHub/官方文档。

## 1. 问题背景

- AutoWSGR 当前 OCR 输入图来自 **scrcpy H264 视频流解码帧**（8Mbps 有损），不是 adb 无损截图。
- 现象：编队页等级（小字数字）反复识别不到；尝试换 EasyOCR 引擎后仍未解决。
- 待验证假设：① scrcpy 画质糊导致 OCR 输入差；② 通用 OCR 模型不认战舰少女R 游戏字体。

## 2. 调研范围

mirrorchyan（https://mirrorchyan.com/zh/projects）上列出的 50+ 开源手游自动化项目，按技术流派归类（已全部核实）：

| 流派 | 代表项目 | 识别核心技术 |
|---|---|---|
| MaaFramework 系（C++，图色识别为主） | MRA《战舰少女R》、MaaYuan、MaaBD2、MAA_SnowBreak、MAA_Punish、MaaFgo、识宝、SSAH、Maa_KES、MaaLYSK、MaaYYs、M9A、火影忍者MAA、MAATree、Maa_MHXY_MG、MaaResonance、MaaEnd、MaaNTE、MaaGF2Exilium、MDA、MaaGakumasu | 模板匹配 + OCR（内置 FastOCR） |
| ALAS 系（Python，OCR 为重） | ALAS（碧蓝）、SRA / StarRailCopilot（星铁） | OCR（自训模型）为主 |
| 独立 Python 系 | BAAS/BAAH（蔚蓝档案）、BlueArchive_Copyninja、LALC/AALC、三月七小助手 | 模板匹配 + 独立 OCR 服务 / RapidOCR |
| PC 后台系（ok-script 系） | ok-gi / ok-gf2 / ok-ww / ok-ef、绝区零一条龙 | OpenCV 模板匹配 + PP-OCR(ONNX) + YOLO |
| 安卓端 | 明日方舟速通（ArkLights） | 无障碍截图 + PaddleOCR + 模板 |
| 其他 | Auto_Resonance（NEMUIPC）、BetterGI（多模型融合）、DoroHelper（AHK FindText）、ok-nte（自研CV+音频）、BetterNTE（Rust） | 多样 |
| 专用 OCR | LuLing-OCR（AutoWSGR 专用） | CRNN 专训模型 |

## 3. 已调研项目详查

### 3.1 MAA（MaaAssistantArknights，明日方舟）

- 截图：**启动时实测各方案自动选最快的**（PR #15608 实测数据）：
  - 模拟器专属增强（MumuExtras / LDExtras / AVD 共享内存）：**0~3ms**（雷电 9 V9.1.32+ / MuMu V4.1.26+ 官方支持）
  - `adb exec-out "screencap | gzip -1"`（raw+gzip，PC 端解压，无损）：**~120ms**
  - `adb exec-out screencap -p`（PNG 设备端编码）：**~370-390ms**，最慢
  - 结论：PNG 编码在模拟器内做很慢，raw+gzip 无损且快 3 倍。
- 识别：静态 UI 以模板匹配为主；OCR 仅用于少量文字（干员名等），支持内置 ONNX PaddleOCR / Windows OCR / RPC 外部服务。
- 触控：minitouch / MaaTouch / maatouch（socket 注入），不用 adb input。
- 文档：https://docs.maa.plus/zh-cn/manual/connection.html

### 3.2 ALAS（AzurLaneAutoScript，碧蓝航线，纯 Python）

- 截图：adbutils + uiautomator2，ADB screencap。性能基准：**低配 >1s、一般 ~0.5s、高配 ~0.3s**（README 明示）。
- OCR（module/ocr/ocr.py，一手源码）：
  - **为游戏字体专门训练模型**：`lang='azur_lane'`、`azur_lane_jp`，bin/ocr 存专训模型。
  - 预处理 `extract_letters`：按文字颜色抽字（白色 RGB 255,255,255）+ 阈值二值化 → 白字黑底单通道再喂 OCR。
  - **字符白名单** `alphabet='0123456789IDSB'`：限定输出字符集。
  - **后处理纠错** `I→1, D→0, S→5, B→8`。
  - 支持 RPC OCR 服务器模式（UseOcrServer）、YUV 亮度通道识别抗颜色干扰。
  - 引擎：cnocr 1.2.2 + mxnet（早期）/ PaddleOCR。
- 仓库：https://github.com/LmeSzinc/AzurLaneAutoScript

### 3.3 SRA / StarRailCopilot（崩坏星穹铁道）

- 基于 ALAS 下一代框架，OCR 管线沿用 ALAS（PaddleOCR/cnocr 系 + 自训模型）。
- **强制推荐模拟器分辨率 1280x720**（和 MAA 一样，低分辨率反而有利于识别稳定）。
- 仓库：https://github.com/LmeSzinc/StarRailCopilot

### 3.4 BAAS（蔚蓝档案）

- **OCR 用 C++ 重构为独立子进程**（BAAS_Cpp），通过 HTTP + 共享内存通信，主程序不背 OCR 负担。
- 用途：BOSS 血量、倒计时、物资数量、关卡 ID、角色名（和 AutoWSGR 的"等级/类型"完全同类）。
- 声称短文本毫秒级；多语言；Windows/Linux/macOS/Android 跨平台预编译。
- 识别分工（官方文档）：静态元素（按钮/图标）用**模板匹配**（1ms 内，CPU 即可）；动态文字用 OCR。
- 仓库：https://github.com/pur1fying/BAAS_Cpp 、https://baas.wiki/develop_doc/script/ocr.html

### 3.5 MRA（战舰少女R 小助手）

- 基于 MaaFramework + MFAAvalonia + MXU，与 AutoWSGR 同游戏竞品。
- 功能：常规图/炸鱼/捞胖次、远征、战役、演习、决战、造船、活动练级。
- 识别：沿用 MaaFramework 的模板匹配为主 + OCR 辅助。
- 官网：https://saratoga-official.github.io/MRA/

### 3.6 LuLing-OCR（AutoWSGR 专用 OCR，重大发现）

- OpenWSGR 组织开源，明写"为 AutoWSGR（战舰少女R 自动化框架）提供游戏 UI 文字识别能力"。
- **CRNN 架构**：5 层 CNN + 2 层 BiLSTM + CTC 解码，8.9M 参数，模型 ~102MB，CPU 推理 < 100ms。
- **大字库**：7000 常用汉字 + 116 符号/字母（共 7117 类）。
- **在线合成训练**：用思源黑体（Source Han Sans SC）字体渲染合成数据，无需收集标注真实截图。
- 预处理：自动颜色通道选择、对比度拉伸、极性检测。
- 仓库：https://github.com/OpenWSGR/LuLing-OCR

### 3.7 Tesseract 系通用实践（轻量脚本）

- 预处理共识：裁剪 ROI → 灰度 + 自适应二值化 → 形态学去噪 → **放大 2-3 倍**（INTER_CUBIC）→ 字符白名单 `tessedit_char_whitelist` → `--psm 7` 单行 / `--psm 6` 文本块。
- 自定义字体：jTessBoxEditor 训练专属 `.traineddata`。
- 参考：https://www.volcengine.com/article/820588

### 3.8 ok-script 系（PC 后台自动化，源码级确认）

统一特征：**PP-OCR 模型转 ONNX + OpenVINO/NPU 加速**（`onnxocr-ppocrv4/v5`），OCR 是"基础设施"而非主力，主力是 OpenCV 模板匹配（COCO 标注素材、多分辨率自适应）+ HSV 找色。

| 项目 | OCR 引擎 | 关键发现 |
|---|---|---|
| ok-script（框架） | 不捆绑，项目自配 | 提供 `wait_click_ocr`、**`add_text_fix` 文字修正表**（对应 AutoWSGR 的 correction rules）、名称匹配支持 str/正则/列表 |
| ok-gi（原神，已停维护） | PP-OCRv4 ONNX + OpenVINO | 模板匹配 + YOLO + OCR 分工；win32 后台截图 |
| ok-gf2（少前2） | PP-OCRv4 ONNX + OpenVINO | **HSV 颜色隔离预处理**（源码 `frame_processs.py` + `hsv_config.py`）：按白/金/灰字 HSV 范围 inRange → 形态学闭运算 → 纯文字图再喂 OCR；README 踩坑"主页背景必须暗色，否则识别不到文字" |
| ok-ww（鸣潮） | PP-OCRv5 ONNX + OpenVINO/NPU | **YOLOv8 ONNX 目标检测**用于声骸/敌人识别（`OnnxYolo8Detect.py`，letterbox + NMS）；声骸文字 OCR 在 GUI 中可开关（耗 CPU） |
| ok-ef（终末地） | PP-OCRv5 ONNX + OpenVINO | OCR 结果接 **CSV 词表匹配/纠错链路**（装备词条识别管线）；有独立《i18n 与 OCR 配置流程》文档 |

### 3.9 绝区零一条龙（ZenlessZoneZero-OneDragon）—— 小字识别参考价值最大

- 截图：mss + pyautogui；OCR 用 **onnxruntime-directml**。
- OCR：自研封装 PP-OCRv5/v6（`onnx_ocr_matcher.py`），`use_angle_cls=False`、`det_limit_side_len=960`。
- 关键工程优化（PR #1756）：
  - **crop_first：先裁剪 ROI 再 OCR**（默认裁剪后识别）；
  - **单行模式 `det=False` 跳过文字检测直接走 rec 识别**（`run_ocr_single_line`，固定区域单行小字又准又快）；
  - **LCS 最长公共子序列模糊匹配**（`match_words`，容忍 OCR 错一两个字）；
  - GPU 线程池串行化 + OCR 结果缓存。
- 链接：https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon

### 3.10 MaaFramework 体系（MRA / MaaYuan / MaaBD2 / MAA_SnowBreak / Maa_KES / MaaLYSK / MaaYYs / M9A / 火影MAA / MAATree / Maa_MHXY_MG / MaaResonance / MaaEnd / MaaNTE / MaaGF2Exilium / MAA_Punish / 识宝 / MDA / MaaGakumasu）

绝大多数是 MaaFramework 的**资源/pipeline 项目**，识别能力即 MaaFramework 内置：

- **识别算法集**：`DirectHit | TemplateMatch | FeatureMatch | ColorMatch | OCR | NeuralNetworkClassify | NeuralNetworkDetect | And/Or | Custom`。**每个节点只能选一种 recognition**，静态 UI 用 TemplateMatch，动态文本用 OCR，多状态用多个节点 + `next` 链顺序尝试。
- **OCR 实现**（`Vision/OCRer.cpp`）：FastDeploy 的 **PPOCRv4（PaddleOCR→ONNX，det+rec+keys.txt）**，模型资产在 MaaCommonAssets 仓库（v3~v6 可选，pipeline `model` 字段指定）。
- **OCR 节点关键字段**：`expected`（精确匹配）、`expected_partial`（正则/包含）、**`replace`（识别结果替换纠错）**、`need_each`、`only_rec`（跳过检测）、`roi`（限定区域）、**`color_filter`（v5.8+，颜色二值化后再 OCR，提升彩色 UI 文字识别）**、同模型 batch 合并。
- **截图**：模拟器 adb screencap（统一缩放到 720p 内部基准）；PC 端 Win32 Desktop Duplication/GDI。
- **统一约束**：模拟器固定分辨率（1280×720 居多）、MaaYYs 提示"队伍预设名避免复杂符号降低 OCR 失败"、Maa_MHXY_MG 有"OCR 回退 V4 模型"实践、MaaGakumasu 用 **YOLOv11 自训模型**识别卡牌 + `replace` 纠错繁简字（`[["费","費"]]`）。
- 突破模板匹配的案例：**BetterGI**（YOLO 目标检测 + PaddleOCR + SIFT/ORB 特征匹配，多模型融合）、**ok-nte**（自研 CV 战斗算法 + 音频触发）、**MaaFgo**（BBchannel 战斗内核 + Maa 视觉导航混合）、**Auto_Resonance**（NEMUIPC MuMu IPC 截图/控制）。

### 3.11 独立 Python 系补充

- **AALC / LALC（Limbus Company）**：均用 **RapidOCR**（PP-OCRv4 ONNX，requirements 实锤）。AALC 截图用 pywin32 GDI BitBlt + PrintWindow 后台；**OCR 前 CLAHE 自适应直方图均衡**（clipLimit=2.0）增强低对比度小字。LALC 用 OpenCV 模板匹配为主 + RapidOCR 辅助，**金字塔多尺度模板匹配**适配分辨率，"精细匹配"场景跳过 CLAHE 保留细节。
- **三月七小助手（星铁）**：RapidOCR + onnxruntime-directml/openvino 硬件加速；mss 截图；OCR 用于资源数值、任务文本。
- **BAAH（蔚蓝档案）**：模板匹配为主（数百张素材）+ **pponnxcr**（PaddleOCR→ONNX）辅助；OCR 用于战术大赛对手排名/等级、咖啡馆学生名；强约束模拟器 **1280×720 / 240DPI**；同名/近似名有专门延迟配置。
- **DoroHelper（Nikke，已归档）**：AutoHotkey V2 + **FindText**（图像转黑白 ASCII 文本匹配，轻量伪 OCR）；README 列了完整"影响识别环境"强制清单（关 HDR/色彩滤镜/悬浮窗、16:9 ≤1080p、60fps）。
- **明日方舟速通（ArkLights，安卓端）**：懒人精灵无障碍截图 + **PaddleOCR**（按需下载）；"保守识别、有问题就保留"置信度策略 + "不使用 OCR"回退开关。

## 4. 核心共识

1. **识别分工**：静态 UI（按钮/图标/页面锚点）一律模板匹配（1ms）；只有动态文字（数值/名称）才上 OCR；需要"找物体/区域"时用 YOLO 类目标检测（ok-ww、BetterGI、MaaGakumasu），**不要把 OCR 当检测器用**。
2. **OCR 输入质量优先**：无损截图是基础。主流两条路：adb raw+gzip（~120ms）或模拟器共享内存/专属 IPC（0-3ms，NEMUIPC、MuMu 增强）。
3. **OCR 引擎选型事实标准 = PP-OCR 系（ONNX 化）**：RapidOCR / onnxocr-ppocrv4/v5 / MaaFramework FastOCR / pponnxcr 全部是 PaddleOCR 模型转 ONNX。**无人用 EasyOCR/Tesseract**。加速用 OpenVINO/DirectML。
4. **OCR 引擎不是关键，预处理才是**：
   - crop_first：**先裁剪 ROI 再 OCR**（OneDragon）；
   - **单行模式 det=False 禁检测直接识别**（OneDragon）——固定位置小字的制胜招；
   - **HSV 颜色隔离**按文字颜色抠出文字层（ok-gf2）、**color_filter 颜色二值化**（MaaFramework v5.8+）、**CLAHE 对比度均衡**（AALC/LALC）；
   - 放大 2-3x + 灰度二值化（Tesseract 系）。
5. **OCR 结果后处理**：`replace` 纠错映射表（MaaFramework 原生字段 / MaaGakumasu 繁简纠错 / ALAS I→1）、LCS 模糊匹配（OneDragon）、字符白名单（ALAS alphabet）、保守识别策略（ArkLights）。
6. **通用模型识别不了游戏字体**：ALAS 专训模型、LuLing-OCR 已为战舰少女R 做好。
7. **环境强约束**：固定模拟器分辨率/DPI、关 HDR/色彩滤镜/悬浮窗（DoroHelper/BAAH/ALAS 一致要求 1280×720）。
8. **性能基准**：adb screencap 一般 ~0.5s；OCR 高频场景需缓存 + 线程池，可做成可开关项。

## 5. 对 AutoWSGR 的建议

- **短期（验证画质）**：`screenshot_native()` 走 `adb exec-out "screencap | gzip -1"`（无损 + ~120ms），与 scrcpy 帧做 A/B 对比。
- **中期（预处理 + 后处理，抄 OneDragon 组合拳）**：
  1. 等级/舰名识别改为 **crop_first + 单行模式（det=False）**，限定 ROI；
  2. 叠加 **HSV 颜色隔离**（等级数字一般是特定颜色）或 CLAHE 增强；
  3. 识别结果用 **LCS 模糊匹配 + replace 纠错映射表** 替代堆叠海量 correction rules。
- **引擎替换**：从 EasyOCR 迁移到 **onnxocr-ppocrv5 / RapidOCR + OpenVINO**（中文小字明显更稳、可 GPU/NPU 加速）。
- **长期（识别率根治）**：直接用或借鉴 **LuLing-OCR**（AutoWSGR 生态现成专训模型）。
- **架构参考**：识别器接口 + 特殊识别器注册（Maa CustomRecognition）；模板匹配/OCR/YOLO 分工明确。

## 6. 参考链接汇总

- MAA：https://docs.maa.plus/zh-cn/manual/connection.html ｜ PR #15608 https://github.com/MaaAssistantArknights/MaaAssistantArknights/pull/15608
- ALAS：https://github.com/LmeSzinc/AzurLaneAutoScript （OCR 源码 module/ocr/ocr.py）
- StarRailCopilot：https://github.com/LmeSzinc/StarRailCopilot
- BAAS：https://baas.wiki/develop_doc/script/ocr.html ｜ https://github.com/pur1fying/BAAS_Cpp
- MRA：https://saratoga-official.github.io/MRA/
- LuLing-OCR：https://github.com/OpenWSGR/LuLing-OCR
- MaaFramework：https://github.com/MaaXYZ/MaaFramework ｜ OCR 实现 https://github.com/MaaXYZ/MaaFramework/blob/main/source/MaaFramework/Vision/OCRer.cpp ｜ 模型资产 https://github.com/MaaXYZ/MaaCommonAssets
- ok-script：https://github.com/ok-oldking/ok-script ｜ ok-gf2：https://github.com/ok-oldking/ok-gf2 ｜ ok-ww：https://github.com/ok-oldking/ok-wuthering-waves ｜ ok-ef：https://github.com/AliceJump/ok-end-field
- 绝区零一条龙：https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon ｜ PR #1756
- 明日方舟速通：https://github.com/AegirTech/ArkLights
- BetterGI：https://github.com/babalae/better-genshin-impact
- MaaGakumasu：https://github.com/SuperWaterGod/MaaGakumasu ｜ replace 纠错 https://github.com/MaaXYZ/MaaFramework/issues/1080
- AALC：https://github.com/KIYI671/AhabAssistantLimbusCompany ｜ LALC：https://github.com/HSLix/LixAssistantLimbusCompany
- 三月七：https://github.com/moesnow/March7thAssistant ｜ BAAH：https://github.com/BlueArchiveArisHelper/BAAH
- MDA：https://github.com/1204244136/MDA ｜ DoroHelper：https://github.com/1204244136/DoroHelper
- Auto_Resonance：https://github.com/Night-stars-1/Auto_Resonance ｜ MaaNTE/ok-nte/BetterNTE：https://github.com/1bananachicken/MaaNTE 等
- 镜像站清单：https://mirrorchyan.com/zh/projects
