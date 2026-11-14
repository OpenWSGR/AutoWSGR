# 决战原始观察采集

采集截图、原始观察和本机验收报告仅保存在仓库外的本地输出目录，不提交到 Git。
随机掉落的舰名和画面不作为通用测试的依赖；结算测试使用可控的页面状态和控件结果，
节点恢复测试使用精简的合成地图与观测。历史本地样本目录
`testing/fixtures/decisive-clear/` 和 `testing/fixtures/decisive-observations/` 已忽略。
生产识别需要的通用控件模板仍位于 `autowsgr/data/images/decisive/`。

在固定提交的独立 worktree 运行，使用现有虚拟环境。首次启动保留当前地图；
如果实际位于主页，则导航到第 6 章，核实小关后进入已有进度，不额外重置。
首轮若出现「重置关卡」入口立即保存现场停止。只有完成本轮三小关后才开始下一轮并正常重置章节。

```powershell
python -m tools.decisive.collect --config D:/Games/autowsgr/user_settings.yaml --output D:/Games/autowsgr/decisive-samples/run-01 --rounds 3 --start-stage 1 --start-node A
```

`--start-node A` 表示调用者已确认当前点位，采集器不会把 native 预测冒充标签。
未知恢复应省略该参数。异常后依据现场确认 `--start-stage`，若已确认节点可同时传入
`--start-node`，用新的输出目录和 `--rounds` 指定剩余轮数，`--round-offset` 指定已完成轮数。
若编队异常停在决战准备页，恢复入口先核对准备页，调用原有回退操作返回当前地图，
核对地图后按原小关／节点继续；不会为此进入总览或重置。回退失败保留现场停止。

已确认完整通关一章、游戏停在入口后，可用 `--start-at-entry --round-offset 1 --rounds 2`
正常重置并采集剩余两章。该入口要求 `round-offset > 0`，不能同时指定恢复节点；
默认入口继续禁止首轮额外重置。总轮数由已完成偏移加本次剩余轮数确定，不额外补跑。

若终点战斗已经完成、进程停在掉落舰船的奖励结算画面，使用
`--resume-stage-clear --start-stage 1 --round-offset 1 --rounds 2` 恢复正在结算的小关。
此入口与 `--start-node`、`--start-at-entry` 互斥，只接受实际掉落页与对话控件；
先完成奖励结算，再以确定 A 进入下一小关，不新建旧小关战斗会话，不重复终点或重置。
例如第 2 轮第一小关的 10 场已经完成时，本次只剩该轮 20 场和第 3 轮 30 场。

只覆盖运行内 `useful_skill=False` 和 `useful_skill_strict=False`，保持原配置文件。
舰队、旗舰、维修设置全部沿用原配置。异常、船坞满、撤退请求或停止时保存现场并退出，
不计作完成节点，也不通过自动重试清空采集进度。

恢复、购买或技能尝试后的库存由生产完整扫描核实；单屏不滚动，溢出列表按完整重叠行
遍历，含在队舰船的六槽快照只在验证返回地图后发布。扫描失败或停止保留旧数据并退出，
不能带着部分库存继续编队、维修或开战。新旧决战换船共用该列表遍历器，逐次重新定位。
候选列表为空时仍须确认未筛选、完整端点和稳定空背景；它只表示没有备用舰船，
在队舰船仍计入完整库存。进入已占用槽时的系统离队卡不计作舰船。

输出包含 `manifest.json`（PID、提交、native 版本、停止入口）、`effective_config.json`、
`effective_log_config.json`、`observations.jsonl`、`progress.json`、`summary.json` 和 `images/`。
输出目录必须为空；已有内容时在连接游戏前停止，防止重新编号覆盖旧图片或混合两次档案。
在输出目录创建空文件 `STOP` 即请求停止；采集器在控制器循环、战斗识别和点击前检查。
PNG 保留索敌匹配帧、战果、地图字母裁剪与通关页面；JSONL 保留原始六槽、中文结果、
阵型 OCR、帧序号、单调采集时间、遭遇 ID 及 native/OCR 耗时。
native 结果直接供本次战斗决策和融合会话使用，不为记录重复识别。采集模式每个遭遇
停采时仍为每个遭遇保留一次稳定地图字母观测，启采时跟随生产读取后续新稳定帧，
同帧不会重复调用 native。定位和裁剪使用同一帧；`used_for_tracking`
单独记录当时生产采样策略。停采时字母只归档，不传给模型，模型继续接受已有敌情。
`combat_end.saw_enemy` 记录本场是否实际采集过敌情，直接战斗且未出现阵型页也能统计索敌缺失。

生产与采集共用 `DecisiveMapController.observe_node()` 的不可变观察元数据：帧、定位、
裁剪范围、原始字符串、首字母解析和分项耗时只计算一次；RGB 裁剪由同一帧与范围派生。
归档 crop 是传给 `ApiDll` 的原始裁剪，后续分辨率适配仍由既有 native 适配器负责。
采集继续跳过非地图页和所有 overlay，生产 `recognize_node()` 的舰队获取返回值保持不变。
缺图标仍记录 `map_missing_icon`；无效首字母在 `map` 中保留原始字符串并标记
`failure=invalid_label`。native 异常先保存 `map_error` 的帧、裁剪、`failure/error` 与耗时，
再停止采集；生产路径仍将该失败作为缺失字母证据。有效字母是否属于当前小关由会话校验。

`predicted_node` 与 `label_node/label_source` 独立记录：标签仅来自人工确认起点、已提交
的成功战斗推进及真实通关／重置。模型改写预测节点不会改写标签，重复战果不重复计步。
新档案的 `encounter_complete.observation` 直接归档生产会话已提交的完成事件，保留真实时间和
遭遇标识；随后停止或等待地图超时不会撤销已经发生的完成事件。
确认 A 才使用确定 A 初始化；未知进度保留全节点候选。索敌未发生记为缺失，
不写入伪造六槽。通关预测仅用于开始检查真实确认控件；控件缺失立即保存现场停止，
完成操作后还必须看到决战入口，才能记录小关完成。采集原始页用于后续构建更具体的
通关页面识别。采集运行内开启 v4 融合回放，文件位于输出目录的 `node-fusion/`，原用户
配置文件保持不变。采集 JSONL 的 `fusion_log`、`encounter_id`、`fusion_event_id` 可以关联
原始图片与融合回放；采集 JSONL 自身仍是原始观察档案，不直接交给模型回放入口。

## 固定版本采集的离线转换

旧采集版本只有原始 JSONL 时，可以转换为每轮、每小关独立的 v4 回放：

```powershell
python -m tools.decisive.replay_collection D:/Games/autowsgr/decisive-fusion-validation/collection-02/observations.jsonl --output D:/Games/autowsgr/decisive-fusion-validation/replay-02
```

转换器一次读取完整换行行的固定快照，正在写入的末尾行留到下次；每次运行新建
`snapshot-*` 目录，不覆盖采集或旧报告。初始化只接受首次观测前的明确标签来源，
后续 `label_node` 和 `predicted_node` 不作为节点证据。native 字母仅来自 `map.raw_node`，
敌情直接复用六槽原始码、中文结果和 OCR，不重新识别图片。新采集记录中的
`used_for_tracking=false` 会保留，旧版本没有此字段时按实际存在的字母观测重放。

新档案优先重放生产会话的显式 `encounter_complete`，不从页面日志再次推测完成。
旧档案的成功 `combat_end` 还需对应 `node_result_after` 确认流程继续，才按唯一遭遇 ID 提交
一次推进；确认前读到的下一节点地图先缓冲，确认后再按完成、地图的因果顺序重建。
旧档案以 `node_result_before` 的单调时间近似完成时刻，报告的 `completion_sources` 明确
区分 `legacy_before_timestamp` 与 `recorded_observation`；近似时间不作为在线一致性证据。
旧档案的停止、失败、未知结果和未完成日志尾部不推测推进。预测通关不能替代
`stage_clear_after` 的操作及返回入口确认。没有索敌且直接进入夜战／战果的遭遇也计入
`enemy_missing`，不依赖阵型页面是否出现。

每个快照包含原始完整行副本、`.jsonl.gz` 回放、独立流程标签、回放摘要及
`validation-report.json`。报告比较的是新模型逐事件重建与离线回放，不证明旧采集进程
已使用新模型控制，也不把确定起点加已确认推进的流程一致率当作准确率校准。
