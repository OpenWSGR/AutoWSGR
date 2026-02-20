# 图像模板使用报告

> 自动生成于文件拆分重构阶段，记录项目中所有图像模板的存储位置、加载机制和引用关系。

---

## 一、图像文件清单

项目共有 **288 个图像模板文件**：282 个旧版资源 + 5 个新版 UI 模板 + 1 个 logo。

### 1.1 新代码模板 (`autowsgr/ui/templates/`)

| 文件 | 用途 |
|------|------|
| `map.png` | 标签页识别 — 地图页 |
| `build.png` | 标签页识别 — 建造页 |
| `intensify.png` | 标签页识别 — 强化页 |
| `mission.png` | 标签页识别 — 任务页 |
| `friend.png` | 标签页识别 — 好友页 |

### 1.2 旧版资源 (`autowsgr_legacy/data/images/`)

| 子目录 | 文件数 | 用途 |
|--------|--------|------|
| `back_buttons/` | 8 | 返回按钮变体 (1-8.PNG) |
| `build_image/ship/` | 4 | 舰船建造 UI (start/complete/fast/full_depot) |
| `build_image/equipment/` | 4 | 装备开发 UI |
| `build_image/` | 1 | 资源选择页面 (resource.PNG) |
| `chapter_image/` | 9 | 章节选择标识 (1-9.PNG) |
| `choose_ship_image/` | 4 | 选船页面标签 (1-4.PNG) |
| `confirm_image/` | 6 | 各种确认弹窗 (1-6.PNG) |
| `decisive_battle_image/` | 9 | 决战模式 UI (1-9.PNG) |
| `error_image/` | 5 | 网络错误/远程登录检测 |
| `event/` | ~70+ | 各活动图片 (按日期/common/enemy 分组) |
| `exercise_image/` | 1 | 演习对手信息 |
| `fight_image/` | 21 | 战斗流程各状态 (1-20.PNG) |
| `fight_result/` | 7 | 战果评级 (SS/S/A/B/C/D/LOOT.PNG) |
| `game_ui/` | 17 | 通用游戏 UI 元素 (1-17.PNG) |
| `identify_images/` | ~30 | 页面识别模板 |
| `normal_map_image/` | ~45 | 普通地图关卡 (1-1 到 9-5.PNG) |
| `restaurant_image/` | 3 | 食堂 (cook/have_cook/no_times.PNG) |
| `shiptype_image/` | ~14 | 舰种识别 (BB1/CV1/DD1...) |
| `start_image/` | 7 | 启动/登录流程 (1-7.PNG) |
| `symbol_image/` | 13 | 通用符号标识 (1-13.PNG) |

---

## 二、核心架构 — 图像模板系统

### 2.1 数据类: `ImageTemplate`

**文件**: `autowsgr/vision/image_template.py`

| 行号 | 内容 |
|------|------|
| L30 | `class ImageTemplate` — 模板图片封装 (name, image ndarray, source) |
| L53 | `from_file()` — 从 PNG 文件加载，内部用 `cv2.imread` (L74) |
| L86 | `from_ndarray()` — 从 numpy 数组创建 |
| L186 | `class ImageRule` — 模板列表 + ROI + 置信度 |
| L233 | `class ImageSignature` — 多 ImageRule 组合签名 |

### 2.2 匹配引擎: `ImageChecker`

**文件**: `autowsgr/vision/image_matcher.py`

| 行号 | 方法 | 说明 |
|------|------|------|
| L65 | `_match_single_template()` | 调用 `cv2.matchTemplate()` (L86) |
| L124 | `match_rule()` | 规则内多模板匹配 |
| L152 | `check_signature()` | 多规则签名匹配 |
| L184 | `find_template()` | 单模板查找 (= 旧 `locate_image_center`) |
| L189 | `find_any()` | 多模板任一匹配 (= 旧 `image_exist`) |
| L198 | `find_best()` | 最高置信度模板 |
| L208 | `find_all()` | 所有匹配模板 |
| L213 | `template_exists()` | 模板是否存在 |
| L220 | `identify()` | 多签名页面识别 |
| L235 | `find_all_occurrences()` | NMS 去重多实例 (L251) |

### 2.3 旧版模板加载

| 文件 | 行号 | 机制 |
|------|------|------|
| `autowsgr_legacy/constants/data_roots.py` | L5 | `IMG_ROOT = join(DATA_ROOT, 'images')` |
| `autowsgr_legacy/constants/image_templates.py` | L9 | `MyTemplate(Template)` — 继承 airtest `Template` |
| `autowsgr_legacy/constants/image_templates.py` | L23 | `IMG = create_namespace(IMG_ROOT, ...)` — 全局模板注册 |
| `autowsgr_legacy/utils/io.py` | L191 | `create_namespace()` — 递归扫描 `*.png` 构建 namespace |
| `autowsgr_legacy/utils/io.py` | L218 | `root.rglob('*.[pP][nN][gG]')` — 枚举所有 PNG |

---

## 三、按模块的图像模板使用详情

### 3.1 `autowsgr/ops/` — 游戏操作模块

#### `autowsgr/ops/image_resources.py` — 模板注册中心

| 行号 | 常量 | 模板路径 | 用途 |
|------|------|----------|------|
| L107 | `Cook.COOK_BUTTON` | `restaurant_image/cook.PNG` | 做菜按钮 |
| L110 | `Cook.HAVE_COOK` | `restaurant_image/have_cook.PNG` | 效果生效弹窗 |
| L113 | `Cook.NO_TIMES` | `restaurant_image/no_times.PNG` | 次数已尽弹窗 |
| L120 | `GameUI.REWARD_COLLECT_ALL` | `game_ui/15.PNG` | 一键领取按钮 |
| L123 | `GameUI.REWARD_COLLECT` | `game_ui/12.PNG` | 单个领取按钮 |
| L130-135 | `Confirm.CONFIRM_1~6` | `confirm_image/1~6.PNG` | 确认弹窗 ×6 |
| L154 | `Build.SHIP_START` | `build_image/ship/start.PNG` | 舰船建造开始 |
| L157 | `Build.SHIP_COMPLETE` | `build_image/ship/complete.PNG` | 舰船建造完成 |
| L162 | `Build.SHIP_FAST` | `build_image/ship/fast.PNG` | 快速建造 |
| L165 | `Build.SHIP_FULL_DEPOT` | `build_image/ship/full_depot.png` | 船坞已满 |
| L171 | `Build.EQUIP_START` | `build_image/equipment/start.PNG` | 装备开发开始 |
| L176 | `Build.EQUIP_COMPLETE` | `build_image/equipment/complete.PNG` | 装备开发完成 |
| L181 | `Build.EQUIP_FAST` | `build_image/equipment/fast.PNG` | 快速开发 |
| L184 | `Build.EQUIP_FULL_DEPOT` | `build_image/equipment/full_depot.PNG` | 仓库已满 |
| L190 | `Build.RESOURCE` | `build_image/resource.PNG` | 资源选择页 |
| L197 | `Fight.NIGHT_BATTLE` | `fight_image/6.PNG` | 夜战确认 |
| L200 | `Fight.RESULT_PAGE` | `fight_image/14.PNG` | 战果页 |
| L213-219 | `FightResult.SS/S/A/B/C/D/LOOT` | `fight_result/*.PNG` | 评级模板 ×7 |
| L230-233 | `ChooseShip.PAGE_1~4` | `choose_ship_image/1~4.PNG` | 选船页标签 ×4 |
| L239 | `Symbol.GET_SHIP` | `symbol_image/8.PNG` | 获取舰船标志 |
| L242 | `Symbol.GET_ITEM` | `symbol_image/13.PNG` | 获取道具标志 |
| L253 | `BackButton.all()` | `back_buttons/1~8.PNG` | 返回按钮 ×8 |
| L260-272 | `Error.*` | `error_image/bad_network*.PNG` 等 | 错误模板 ×5 |

#### `autowsgr/ops/build.py` — 建造操作

| 行号 | 模板 | 用途 |
|------|------|------|
| L71 | `Templates.Symbol.GET_SHIP/GET_ITEM` | 获取舰船判断 |
| L84 | `Confirm.all()` | 确认弹窗 |
| L142-144 | `Build.SHIP_FAST/EQUIP_FAST` | 快速建造 |
| L162-167 | `Build.*_COMPLETE/*_FULL_DEPOT` | 完成/仓库满 |
| L242 | `Build.*_START` | 开始建造 |
| L257 | `Build.RESOURCE` | 资源页面 |

#### `autowsgr/ops/cook.py` — 食堂操作

| 行号 | 模板 | 用途 |
|------|------|------|
| L128 | `Cook.COOK_BUTTON` | 做菜按钮 |
| L139 | `Cook.HAVE_COOK` | 效果生效 |
| L146 | `Cook.NO_TIMES` | 次数已尽 |

#### `autowsgr/ops/reward.py` — 任务奖励

| 行号 | 模板 | 用途 |
|------|------|------|
| L56 | `Confirm.all()` | 确认弹窗 |
| L107 | `GameUI.REWARD_COLLECT_ALL` | 一键领取 |
| L121 | `GameUI.REWARD_COLLECT` | 单个领取 |

#### `autowsgr/ops/expedition.py` — 远征

| 行号 | 模板 | 用途 |
|------|------|------|
| L63 | `Confirm.all()` | 确认远征弹窗 |

---

### 3.2 `autowsgr/combat/` — 战斗系统

#### `autowsgr/combat/recognizer.py` — 战斗状态视觉识别

| 行号 | 战斗状态 | template_key | 对应图像 | 用途 |
|------|----------|--------------|----------|------|
| L63 | `PROCEED` | `fight_image[5]` | `fight_image/5.PNG` | 继续前进/回港 |
| L68 | `FIGHT_CONDITION` | `fight_image[10]` | `fight_image/10.PNG` | 战况选择 |
| L72 | `SPOT_ENEMY_SUCCESS` | `fight_image[2]` | `fight_image/2.PNG` | 索敌成功 |
| L76 | `FORMATION` | `fight_image[1]` | `fight_image/1.PNG` | 阵型选择 |
| L80 | `MISSILE_ANIMATION` | `fight_image[20]` | `fight_image/20.png` | 导弹动画 |
| L84 | `FIGHT_PERIOD` | `symbol_image[4]` | `symbol_image/4.png` | 战斗进行中 |
| L88 | `NIGHT_PROMPT` | `fight_image[6]` | `fight_image/6.PNG` | 夜战提示 |
| L93 | `RESULT` | `fight_image[3]` | `fight_image/3.PNG` | 战果结算 |
| L97 | `GET_SHIP` | `symbol_image[8,13]` | `symbol_image/8,13.PNG` | 获取舰船/道具 |
| L102 | `FLAGSHIP_SEVERE_DAMAGE` | `fight_image[4]` | `fight_image/4.PNG` | 旗舰大破 |
| L106 | `MAP_PAGE` | `identify_images.map_page` | `identify_images/map_page.PNG` | 地图页 |
| L110 | `BATTLE_PAGE` | `identify_images.battle_page` | `identify_images/battle_page.PNG` | 战役页 |
| L114 | `EXERCISE_PAGE` | `identify_images.exercise_page` | `identify_images/exercise_page*.png` | 演习页 |
| L133-140 | 评级 | `fight_result[SS/S/A/B/C/D]` | `fight_result/*.PNG` | 战果等级 ×6 |

#### `autowsgr/combat/handlers.py` — 状态处理器

| 行号 | template_key | 用途 |
|------|--------------|------|
| L176 | `fight_image[13]` | 检查迂回按钮 |
| L215 | `fight_image[13]` | 点击迂回 |
| L231 | `fight_image[17]` | 远程导弹支援 |
| L396 | `fight_image[4]` | 旗舰大破确认 |

#### `autowsgr/combat/engine.py` — 战斗引擎

| 行号 | 内容 |
|------|------|
| L88-90 | `image_exist` / `click_image` 回调函数声明 |
| L105-106 | 构造函数接收图像回调 |
| L338-352 | `run_combat()` 传递 image 回调 |

---

### 3.3 `autowsgr/ui/` — UI 页面识别

#### `autowsgr/ui/tabbed_page.py` — 标签页模板匹配

| 行号 | 内容 | 模板 |
|------|------|------|
| L127 | `_TEMPLATE_DIR = .../templates` | 模板目录定义 |
| L149-172 | `_load_templates()` | 加载 5 个二值化模板 |
| L160 | MAP → `map.png` | 地图标签 |
| L161 | BUILD → `build.png` | 建造标签 |
| L162 | INTENSIFY → `intensify.png` | 强化标签 |
| L163 | MISSION → `mission.png` | 任务标签 |
| L164 | FRIEND → `friend.png` | 好友标签 |
| L170 | `cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)` | 图像加载 |
| L218-238 | `_coverage()` | 二值模板覆盖度匹配 |

**纯像素匹配页面**（使用 `PixelSignature`，不使用图像模板）：

- `backyard_page.py` — 后院页面
- `main_page.py` — 主页面
- `bath_page.py` — 浴室页面
- `canteen_page.py` — 食堂页面
- `friend_page.py` — 好友页面
- `overlay.py` — 弹窗层
- `decisive_battle_page.py` — 决战页面

---

### 3.4 `autowsgr/vision/` — 视觉子系统

| 文件 | 行号 | 内容 |
|------|------|------|
| `image_template.py` | L74 | `cv2.imread(str(p), cv2.IMREAD_COLOR)` — 模板文件加载 |
| `image_matcher.py` | L86 | `cv2.matchTemplate(screen_gray, template_gray, method)` — 核心匹配 |
| `image_matcher.py` | L251 | `cv2.matchTemplate(...)` — 多实例检测 |
| `pixel.py` | — | `PixelSignature` — 纯像素颜色匹配，不使用图像模板 |
| `matcher.py` | — | `PixelChecker` — 像素特征检测引擎 |

---

### 3.5 `autowsgr_legacy/` — 旧版代码

#### 战斗模块 (`autowsgr_legacy/fight/`)

**normal_fight.py**:

| 行号 | 模板键 | 用途 |
|------|--------|------|
| L30 | `IMG.identify_images.map_page` | 地图页面识别 |
| L31 | `IMG.symbol_image[8], [13]` | 获取舰船/道具 |
| L79-88 | `fight_image[5,10,2,1,20], symbol_image[4], fight_image[6,3,4]` | 战斗全流程 |
| L116 | `IMG.confirm_image[3]` | 确认弹窗 |
| L134-136 | `IMG.fight_image[7,8]` | 战况判断 |
| L340 | `IMG.identify_images['fight_prepare_page']` | 出击准备页 |
| L438 | `IMG.fight_image[4]` | 旗舰大破 |

**battle.py**:

| 行号 | 模板键 | 用途 |
|------|--------|------|
| L40-45 | `fight_image[5,2,1,6,16], symbol_image[4]` | 战役各状态 |
| L47 | `IMG.identify_images.battle_page` | 战役页面 |
| L98 | `fight_image[9,15]` | 难度判断 |

**exercise.py**:

| 行号 | 模板键 | 用途 |
|------|--------|------|
| L95 | `IMG.identify_images['exercise_page']` | 演习页 |
| L97 | `IMG.identify_images['fight_prepare_page']` | 出击准备 |
| L98-103 | `fight_image[2,1,6,3], symbol_image[4]` | 演习各状态 |

**decisive_battle.py**:

| 行号 | 模板键 | 用途 |
|------|--------|------|
| L257 | `IMG.fight_image[18:20]` | 决战特有状态 |
| L302 | `IMG.decisive_battle_image[1]` | 决战入口 |
| L582 | `IMG.symbol_image[12]` | 决战符号 |
| L638 | `IMG.confirm_image[1:]` | 确认弹窗 |
| L698 | `IMG.choose_ship_image[1:3,4]` | 选船 |
| L803 | `IMG.fight_image[3]` | 结果页面 |

**common.py**:

| 行号 | 模板键 | 用途 |
|------|--------|------|
| L33 | `IMG.symbol_image[3]` | 符号检测 |
| L35 | `IMG.symbol_image[9]` | 符号检测 |
| L51 | `IMG.fight_image[14]` | MVP 页面 |
| L615 | `IMG.fight_image[13]` | 迂回按钮 |
| L685 | `IMG.fight_image[17]` | 远程支援 |

**event/event.py**:

| 行号 | 模板键 | 用途 |
|------|--------|------|
| L15 | `IMG.event[event_name]` | 活动特有图片 (动态) |
| L16 | `IMG.event['common']` | 通用活动图片 |
| L17 | `IMG.event['enemy']` | 敌舰类型识别 |
| L103 | `IMG.identify_images['fight_prepare_page']` | 出击准备 |

#### 定时器 (`autowsgr_legacy/timer/timer.py`)

| 行号 | 模板键 | 用途 |
|------|--------|------|
| L176-237 | `IMG.start_image[2-7]` | 启动/登录流程各阶段 |
| L223 | `IMG.game_ui[3]` | 通用 UI |
| L274 | `IMG.error_image['user_remote_login']` | 远程登录检测 |
| L289-327 | `IMG.symbol_image[10], error_image['bad_network'], error_image['network_retry']` | 网络错误处理 |
| L360 | `IMG.identify_images[name]` | 动态页面识别 |
| L533 | `IMG.back_buttons[1:]` | 返回按钮 |
| L588-598 | `IMG.confirm_image[1:]` | 确认弹窗处理 |
| L622-625 | `IMG.game_ui[6], fight_image[3]` | 战果判断 |

#### 其他旧版模块

| 文件 | 模板键 | 用途 |
|------|--------|------|
| `game/build.py` | `IMG.build_image[type].*` | 建造全流程 |
| `game/game_operation.py` | `IMG.symbol_image[8,13], fight_image[6,14]` | 获取舰船/夜战/MVP |
| `game/game_operation.py` | `IMG.choose_ship_image[1,2]` | 选船 |
| `game/get_game_info.py` | `IMG.fight_image[12]` | 血量检测 |
| `port/ship.py` | `IMG.identify_images['fight_prepare_page']` | 出击准备 |
| `port/ship.py` | `IMG.choose_ship_image[1:3,4,3]` | 选船操作 |

---

## 四、完整模板键 → 图像文件映射表

| template_key | 文件路径 (相对 `autowsgr_legacy/data/images/`) | 新代码常量 |
|---|---|---|
| `fight_image[1]` | `fight_image/1.PNG` | recognizer 引用 |
| `fight_image[2]` | `fight_image/2.PNG` | recognizer 引用 |
| `fight_image[3]` | `fight_image/3.PNG` | recognizer 引用 |
| `fight_image[4]` | `fight_image/4.PNG` | handlers 引用 |
| `fight_image[5]` | `fight_image/5.PNG` | recognizer 引用 |
| `fight_image[6]` | `fight_image/6.PNG` | `Templates.Fight.NIGHT_BATTLE` |
| `fight_image[7]` | `fight_image/7.png` | legacy only |
| `fight_image[8]` | `fight_image/8.PNG` | legacy only |
| `fight_image[9]` | `fight_image/9.PNG` | legacy only |
| `fight_image[10]` | `fight_image/10.PNG` | recognizer 引用 |
| `fight_image[11]` | `fight_image/11.PNG` | **未使用** |
| `fight_image[12]` | `fight_image/12.PNG` | legacy: 血量检测 |
| `fight_image[13]` | `fight_image/13.PNG` | handlers: 迂回按钮 |
| `fight_image[14]` | `fight_image/14.PNG` | `Templates.Fight.RESULT_PAGE` |
| `fight_image[15]` | `fight_image/15.PNG` | legacy: 难度 |
| `fight_image[16]` | `fight_image/16.png` | legacy: 战役结果 |
| `fight_image[17]` | `fight_image/17.PNG` | handlers: 远程支援 |
| `fight_image[18]` | `fight_image/18.png` | legacy: 决战 |
| `fight_image[19]` | `fight_image/19.png` | legacy: 决战 |
| `fight_image[20]` | `fight_image/20.png` | recognizer: 导弹动画 |
| `symbol_image[3]` | `symbol_image/3.PNG` | legacy: 符号检测 |
| `symbol_image[4]` | `symbol_image/4.png` | recognizer: 战斗中 |
| `symbol_image[8]` | `symbol_image/8.PNG` | `Templates.Symbol.GET_SHIP` |
| `symbol_image[9]` | `symbol_image/9.PNG` | legacy: 符号检测 |
| `symbol_image[10]` | `symbol_image/10.PNG` | legacy: 错误处理 |
| `symbol_image[12]` | `symbol_image/12.png` | legacy: 决战 |
| `symbol_image[13]` | `symbol_image/13.PNG` | `Templates.Symbol.GET_ITEM` |
| `confirm_image[1-6]` | `confirm_image/1~6.PNG` | `Templates.Confirm.*` |
| `fight_result[SS/S/A/B/C/D/LOOT]` | `fight_result/*.PNG` | `Templates.FightResult.*` |
| `back_buttons[1-8]` | `back_buttons/1~8.PNG` | `Templates.BackButton.all()` |
| `game_ui[3]` | `game_ui/3.PNG` | legacy only |
| `game_ui[6]` | `game_ui/6.PNG` | legacy only |
| `game_ui[12]` | `game_ui/12.PNG` | `Templates.GameUI.REWARD_COLLECT` |
| `game_ui[15]` | `game_ui/15.PNG` | `Templates.GameUI.REWARD_COLLECT_ALL` |
| `choose_ship_image[1-4]` | `choose_ship_image/1~4.PNG` | `Templates.ChooseShip.*` |
| `build_image/ship/*` | 4 files | `Templates.Build.SHIP_*` |
| `build_image/equipment/*` | 4 files | `Templates.Build.EQUIP_*` |
| `build_image/resource` | 1 file | `Templates.Build.RESOURCE` |
| `error_image/*` | 5 files | `Templates.Error.*` |
| `restaurant_image/*` | 3 files | `Templates.Cook.*` |
| `identify_images/*` | ~30 files | legacy 动态引用 |
| `start_image[1-7]` | 7 files | legacy timer 专用 |
| `chapter_image[1-9]` | 9 files | legacy 章节选择 |
| `normal_map_image/*` | ~45 files | legacy 地图识别 |
| `decisive_battle_image[1-9]` | 9 files | legacy 决战 |
| `shiptype_image/*` | ~14 files | legacy 舰种识别 |
| `exercise_image/rival_info` | 1 file | legacy 演习 |
| `event/**` | ~70+ files | legacy 活动 (动态) |

---

## 五、`cv2` 调用点汇总

| 调用类型 | 位置 | 行号 |
|----------|------|------|
| `cv2.matchTemplate` | `autowsgr/vision/image_matcher.py` | L86, L251 |
| `cv2.imread` | `autowsgr/vision/image_template.py` | L74 |
| `cv2.imdecode` | `autowsgr/ui/tabbed_page.py` | L170 |
| `cv2.imdecode` | `testing/test_integration.py` | L134 |
| `cv2.imread` | `tools/pixel_marker.py` | L396 |
| `cv2.imread` | `tools/map_recognize.py` | L331 |
| `cv2.imdecode` | `tools/build_test_dataset.py` | L135 |
| `cv2.imread` | `autowsgr_legacy/timer/backends/ocr_backend.py` | L293 |

---

## 六、统计总结

| 维度 | 数量 |
|------|------|
| 图像模板文件总数 | **288** (282 legacy + 5 新 + 1 logo) |
| `_LazyTemplate` 新代码注册 | **38** 个模板 |
| `cv2.matchTemplate` 调用点 | **2** |
| `cv2.imread` / `cv2.imdecode` 调用点 | **~10** |
| `ImageChecker` 业务调用点 | **~20** (build/cook/reward/expedition) |
| 旧代码 `IMG.*` 引用点 | **~100+** (timer/fight/game/port) |
| 战斗 recognizer 状态签名 | **13** 个 + **6** 评级模板 |
| 旧版 `identify_images/` 页面模板 | **~30** 个 (动态访问) |
| 图像目录/路径常量 | `_IMG_ROOT` (新), `IMG_ROOT` (旧), `_TEMPLATE_DIR` (UI) |

---

## 七、新版检测方式对比分析

新版相比旧版引入了三种检测方式，部分场景已不再依赖图像模板：

| 检测方式 | 新代码中的使用场景 |
|----------|------------------|
| **PixelSignature** (像素颜色匹配) | 所有 UI 页面识别（主页、出征准备、后院、浴室、食堂、决战入口等） |
| **TabbedPage** (二值化+像素覆盖率) | 标签页类型识别（地图/建造/强化/任务/好友），使用 `autowsgr/ui/templates/` 下的 5 张新模板 |
| **OCR** (文字识别) | 章节/地图标题识别，替代了旧版全部 `chapter_image/` 和 `normal_map_image/` |
| **ImageChecker** (OpenCV 模板匹配) | 仍保留：具体 UI 按钮检测（建造、做菜、确认弹窗、战果评级、错误弹窗等） |

---

## 八、可确定不再需要的模板

以下旧版模板在新代码中已有等效实现，可以安全废弃：

### 8.1 已被 PixelSignature 替代（页面识别）

原 `identify_images/` 中以下文件已完全由像素签名替代，**无需保留**：

| 文件 | 被替代方式 |
|------|-----------|
| `main_page.PNG` | `MainPage.PAGE_SIGNATURE` |
| `fight_prepare_page.PNG` | `BattlePreparationPage` 血量栏+面板颜色识别 |
| `backyard_page.PNG` | `BackyardPage.PAGE_SIGNATURE` |
| `bath_page.PNG` | `BathPage.PAGE_SIGNATURE` |
| `canteen_page.PNG` | `CanteenPage.PAGE_SIGNATURE` |
| `choose_repair_page.PNG` | 修理页 `PixelSignature` |
| `decisive_map_entrance.PNG` | `DecisiveBattlePage.PAGE_SIGNATURE` |
| `decisive_battle_entrance.PNG` | 同上 |

### 8.2 已被 TabbedPage 替代（标签页识别）

以下 `identify_images/` 模板已被 `TabbedPage` 覆盖率匹配替代，**无需保留**：

`build_page1/2/3.PNG`、`develop_page1/2/3.PNG`、`destroy_page.PNG`、`discard_page.PNG`、`intensify_page.PNG`、`skill_page1/2.PNG`、`mission_page.PNG`、`friend_page.PNG`、`friend_home_page.PNG`、`expedition_page1/2/3.PNG`

### 8.3 已被 OCR 替代（地图/章节识别）

| 目录 | 文件数 | 被替代方式 |
|------|--------|-----------|
| `chapter_image/` | 9 | OCR 章节标题识别 |
| `normal_map_image/` | ~45 | OCR + 像素坐标扫描 |

### 8.4 新代码未实现的功能（功能未移植，模板暂时无用）

> 注意：这些功能尚未在新版实现，但**将来实现时仍需要这些模板**（或新拍截图），不同于"被更好方式替代"的情况。

| 目录 | 文件数 | 说明 |
|------|--------|------|
| `start_image/` | 7 | 登录流程，新代码未实现 |
| `decisive_battle_image/` | 9 | 决战操作逻辑，新代码未实现 |
| `event/` | ~70+ | 活动地图，新代码未实现 |
| `shiptype_image/` | ~14 | 舰种过滤，新代码未实现 |
| `exercise_image/rival_info.PNG` | 1 | 演习对手信息，新代码未实现 |
| `game_ui/`（除 12、15）| 15 | 其余 UI 元素，新代码未使用 |
| `symbol_image/`（除 4、8、13）| 10 | 旧版杂项符号，新代码未使用 |
| `fight_image/`（除下表保留项）| 9 | 部分旧战斗逻辑 |

`fight_image/` 中不再需要的具体编号：
- `7.png` — 旧版战况判断（新代码用阵型界面不同逻辑）
- `8.PNG` — 旧版战况判断
- `9.PNG` — 旧版战役难度
- `11.PNG` — 从未被引用（旧版亦未使用）
- `12.PNG` — 血量条检测（新代码用像素颜色识别）
- `15.PNG` — 旧版战役难度
- `16.png` — 旧版战役结果
- `18.png`、`19.png` — 决战特有状态（功能未移植）

---

## 九、新版必须保留的模板

**直接被新代码 `ImageChecker` 引用的模板，缺少任何一个将导致功能中断：**

### 9.1 战斗系统（`combat/recognizer.py` + `combat/handlers.py`）

| 文件 | 用途 |
|------|------|
| `fight_image/1.PNG` | 阵型选择界面识别 |
| `fight_image/2.PNG` | 索敌成功界面识别 |
| `fight_image/3.PNG` | 战果结算界面识别 |
| `fight_image/4.PNG` | 旗舰大破提示识别+点击 |
| `fight_image/5.PNG` | 继续前进/回港选择识别 |
| `fight_image/6.PNG` | 夜战提示界面识别 |
| `fight_image/10.PNG` | 战况分析界面识别 |
| `fight_image/13.PNG` | 迂回战术按钮识别+点击 |
| `fight_image/14.PNG` | 战果页面识别（`Fight.RESULT_PAGE`） |
| `fight_image/17.PNG` | 远程导弹支援按钮识别+点击 |
| `fight_image/20.png` | 导弹动画帧识别 |
| `symbol_image/4.png` | 战斗进行中标志识别 |
| `symbol_image/8.PNG` | 获取舰船 |
| `symbol_image/13.PNG` | 获取道具 |
| `identify_images/map_page.PNG` | 战斗结束后返回地图识别 |
| `identify_images/battle_page.PNG` | 战役结束后返回战役页识别 |
| `identify_images/exercise_page1.png` | 演习结束后返回演习页识别 |
| `fight_result/SS.PNG` ... `LOOT.PNG` | 战果等级评定（×7） |

### 9.2 建造系统（`ops/build.py`）

| 文件 | 用途 |
|------|------|
| `build_image/ship/start.PNG` | 开始建造按钮 |
| `build_image/ship/complete.PNG` | 建造完成标志 |
| `build_image/ship/fast.PNG` | 快速建造按钮 |
| `build_image/ship/full_depot.png` | 船坞已满提示 |
| `build_image/equipment/start.PNG` | 开始开发按钮 |
| `build_image/equipment/complete.PNG` | 开发完成标志 |
| `build_image/equipment/fast.PNG` | 快速开发按钮 |
| `build_image/equipment/full_depot.PNG` | 仓库已满提示 |
| `build_image/resource.PNG` | 资源选择页面标志 |

### 9.3 食堂（`ops/cook.py`）

| 文件 | 用途 |
|------|------|
| `restaurant_image/cook.PNG` | 做菜按钮 |
| `restaurant_image/have_cook.PNG` | 效果生效弹窗 |
| `restaurant_image/no_times.PNG` | 次数已尽弹窗 |

### 9.4 通用 UI（多个模块共用）

| 文件 | 用途 |
|------|------|
| `confirm_image/1.PNG` ... `6.PNG` | 各类确认弹窗（×6） |
| `back_buttons/1.PNG` ... `8.PNG` | 返回按钮变体（×8） |
| `game_ui/12.PNG` | 单个任务领取按钮 |
| `game_ui/15.PNG` | 一键全部领取按钮 |

### 9.5 错误处理（`ops/image_resources.py`）

| 文件 | 用途 |
|------|------|
| `error_image/bad_network1.PNG` | 断网提示 |
| `error_image/bad_network2.PNG` | 断网提示变体 |
| `error_image/network_retry.PNG` | 网络重试按钮 |
| `error_image/user_remote_login.PNG` | 异地登录提示 |
| `error_image/remote_login_confirm.PNG` | 异地登录确认 |

### 9.6 选船（`ops/image_resources.py`，功能已注册但未完整实现）

| 文件 | 用途 |
|------|------|
| `choose_ship_image/1.PNG` ... `4.PNG` | 选船页面标签（×4） |

### 9.7 新版专属模板（`autowsgr/ui/templates/`）

| 文件 | 用途 |
|------|------|
| `map.png` | 地图标签覆盖度识别 |
| `build.png` | 建造标签覆盖度识别 |
| `intensify.png` | 强化标签覆盖度识别 |
| `mission.png` | 任务标签覆盖度识别 |
| `friend.png` | 好友标签覆盖度识别 |

---

## 十、汇总

| 分类 | 数量 | 说明 |
|------|------|------|
| **新版必须保留** | **~55 个** | 9.1–9.7 所列全部 |
| **已被更好方式替代，可删除** | **~50 个** | 第 8.1–8.3 节（PixelSig + OCR + TabbedPage） |
| **功能未移植，暂时无用** | **~180 个** | 第 8.4 节（待实现时重新评估） |
| **新版专属（新建）** | **5 个** | `autowsgr/ui/templates/` |
