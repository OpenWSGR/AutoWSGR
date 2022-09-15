## 项目简介

一个战舰少女R的自动化脚本，整合了收集数据的功能。  
[开发笔记](https://www.notion.so/WSR-4bce2f550be14711a576465e72f41c12)

### Current Work

见开发笔记。  

### 提示

新的分支已经创建，请勿改动 `main` 中内容，请在对应分支编写测试并最终合并.  
用的时候在 `usage` 里改代码，不要动其它分支了。

### 环境和语言

- python:`3.7.4-64bit`
- c++:`c++17`
- system:`win10-64`

### 功能

提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口。

- `ctrl+alt+c` 终止所有操作并退出程序

### 默认设置

- 进入任何战斗前都将会修理队伍中中破或大破的舰船

### 日志分级

- `DEBUG` 调试级信息，输出所有运行 `api` 级过程
- `INFO1` 1 级操作信息，输出单个操作（点击，滑动操作）
- `INFO2` 2 级操作信息，游戏基本操作（切换界面，战斗子阶段）
- `INFO3` 3 级操作信息，游戏操作（ 暴露的 `api` 的操作）
- `ERROR` 错误，记录所有异常信息
- `CRITICAL` 核心信息，记录可能由程序逻辑错误引起的错误


### 一些参数的规定:

- 舰船血量状态 `Timer.ship_status` : 0 为绿血，1 为黄血，2 为红血，-1 为不存在
- 敌方阵容字典 `Timer.enemy_type_count` : keys() 为所有舰船类型，item 结构为 (类型, 数量)，可以参考 `DecisionBlock`  类中的 `old_version` 成员函数

## 使用

当前 `main` 分支可能存在 `bug`，所以请下载 `Release` 中的源代码并按照以下参考进行构建，以第一份 `Release` 为例，简单介绍构建和使用。

### 环境准备

- Windows10
- Python3.7.x

[安装Python](https://zhuanlan.zhihu.com/p/111168324)

推荐在虚拟环境中运行程序，可以按照下面的教程准备。

#### virtualenv 搭建运行环境

`pip install -r requirements.txt`

#### Anaconda 搭建运行环境（推荐）

咕咕咕

### 接口使用

首先该项目仍处于测试和功能完善状态，且用户 GUI 界面的设计工作优先级较低，所以很长一段时间都只会提供对应的接口，下面简单介绍接口的使用。

#### 设置

路径为 `settings.yaml`，**请自行创建该文件**，可以直接复制 `settings_example.yaml`。

该文件应该是这个样子，你只需要修改 `LDPLAYER_ROOT` 变量的值，修改为你的雷电模拟器所在目录。

请确保雷电模拟器应用程序名为 `dnplayer.exe`，程序将使用 `{LDPLAYER_ROOT}\dnplayer.exe` 命令启动模拟器。

```yaml
LDPLAYER_ROOT: C:\leidian\LDPlayer9
TUNNEL_PATH: data\tunnel
LOG_PATH: data\log
DELAY: 2

DEBUG: False
SHOW_MAP_NODE: False
SHOW_ANDROID_INPUT: False
SHOW_ENEMY_RUELS: False
SHOW_FIGHT_STAGE: False
SHOW_CHAPTER_INFO: False
SHOW_MATCH_FIGHT_STAGE: False
```

#### 计划

所有战斗的决策和控制工作将按照计划中的参数进行，建议将所有计划放在 `plans` 文件夹下，该文件夹中有一些已经写好的计划示例。

进行一场战斗需要两个计划，一个为默认计划，另一个为当前计划，当前计划指定的参数将覆盖默认计划的参数，当前计划未指定的参数将使用默认计划的参数，**默认计划的任何参数均不能缺省，否则可能导致运行时错误**。

演习和其它战斗计划的格式不同，请自行阅读 `\plans` 中的示例，其中有说明。

### 运行

请导入 `wsgr` 模块以调用提供的接口，可以参考 `example.py` 中的示例。

## 补充
### OpenCv 相关的一些报错：
如果出现以下报错，请将 `opencv` 降级为 `4.5.4` 版本。  
```
AttributeError: module 'cv2' has no attribute 'gapi_wip_gst_GStreamerPipeline'
```
`pip uninstall opencv-python`  
`opencv-python==4.5.4.60`  
### 找不到文件的报错
```
FileNotFoundError: [Errno 2] No such file or directory: '.\\Data\\Tmp\\screen.PNG'
```
请在 `data` 目录下创建一个 `tmp` 文件夹，不需要其它任何操作，这个 `bug` 将在不久后修复。

