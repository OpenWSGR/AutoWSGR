## AutoWSGR

![](https://img.shields.io/github/repo-size/huan-yp/Auto-WSGR) ![](https://img.shields.io/pypi/v/AutoWSGR) ![](https://img.shields.io/pypi/dm/AutoWSGR) ![](https://img.shields.io/github/issues/huan-yp/Auto-WSGR) ![MIT licensed](https://img.shields.io/badge/license-MIT-brightgreen.svg)

用python与c++实现的战舰少女R的自动化流水线 & 数据统计一体化脚本，提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口

用户交流, 意见反馈 qq 群:  568500514

## 近期更新

![image-20230226001532677](assets/image-20230226001532677.png)

- GUI上线测试，详情请见：[AutoWSGR-GUI](https://github.com/Nickydusk/AutoWSGR-GUI) - *2023/2/26*
- 支持了当前活动 "炽热星辰行动" - *2023/1/20*
- 解装升级为更快的 "一键解装" - *2023/1/12*
- 支持了在配置方案中指定舰船 - *2023/1/6*


## 功能

- 无间断重复远征
- 自动点击完成任务
- 全自动出征，可通过简单的描述文本实现高可复用的自定义策略
  - 支持：战役、演习、常规战、当前活动地图
  - 即将支持：所有类型活动图、决战
- 支持多种修理模式：快修大破、快修中破、澡堂修理（可指定船名）
- 强容错性
  - 任何游戏界面，返回主页面，处理各种特殊点击需求
  - 游戏卡死、断网时自动重启游戏、模拟器
- `ctrl+alt+c` 终止所有操作并退出程序

## 配置

### 前期准备


安装 [Python](https://www.python.org/) >= 3.7, <=3.9，[雷电模拟器](https://www.ldmnq.com/)，[战舰少女R](http://www.jianniang.com/)

将模拟器设置为 `>=1280x720` 的 `16:9` 分辨率。

![image-20221006213603676](.assets/LeidianResolution.png)

### 安装pytorch

AutoWSGR采用基于神经网络的视觉模型进行图像识别和文字解读，安装GPU版本的pytorch可以加快所有图像操作速度：

```bash
pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu117
```

如果你没有英伟达显卡，则用以下命令安装CPU版本（稍微慢点，不影响使用）：
```bash
pip install torch torchvision torchaudio
```


### 安装AutoWSGR

AutoWSGR 目前已支持通过 [PyPI](https://pypi.org/project/AutoWSGR/) 进行部署，您可以通过以下命令一键安装正式发布版：

```bash
pip install -U AutoWSGR
```

你也可以通过以下命令从 GitHub 安装最新版（推荐，本项目尚处于开发早期，这里bug修复更及时）：

```bash
pip install -U git+https://github.com/huan-yp/Auto-WSGR.git@main
```



## 快速使用

- 配合前端使用：详见 [AutoWSGR-GUI](https://github.com/Nickydusk/AutoWSGR-GUI)

- 纯后端使用：样例代码在本项目的`examples/`文件夹下，建议先尝试一体化日常挂机策略（`examples/auto_daily.py`），在使用前你需要更改如下设置：

  - 将`user_settings.yaml`中的**LDPLAYER_ROOT**属性替换为您的雷电模拟器安装根目录

    ```yaml
    LDPLAYER_ROOT: C:\leidian\LDPlayer9
    ```


  - 此外请确保雷电模拟器应用程序名为 `dnplayer.exe`，AutoWSGR将使用 `{LDPLAYER_ROOT}\dnplayer.exe` 命令启动模拟器。


## 启用高级功能

目前的高级功能主要指基于 `easyocr` 的，需要文字识别的功能，请按照以下说明进行配置。

**该功能要求分辨率在 `1280x720` 及以上，推荐使用 `1280x720`**

目前有以下功能属于高级功能：

- 自动化决战

### 配置 ship_name.yaml

启用基于舰船识别功能需要配置 `ship_name.yaml` 文件，该文件相对路径为 `AutoWSGR/data/ocr/ship_name.yaml`

请将同一目录下的 `shipname_example.yaml` 文件复制进去，并对照您的船舱修改对应舰船名

`shipname_example.yaml` 文件中所有舰船名和游戏图鉴保持一致，当前更新到絮弗伦版本，欢迎 PR。

如果某一舰船有多艘，请使用以下格式填写：

```yaml
No.1: # 胡德
	- 胡德荣耀
	- 胡德飙车
	- 胡德未改
```

**注意，对于名字为一个字符的舰船，例如 "鹰"(某未改潜艇)，识别效果较差，如果需要使用，请自行改为两字或以上。**

本项目通过**舰船名字**唯一区分舰船，**如果两艘舰船为同一名字（例如战列狮和战巡狮），那么她们被认为是同一艘舰船，为了避免出现不必要的麻烦，请保证需要使用到的舰船没有同名。**

**另外，由于 `easyocr` 工具本身可能没有收录一些中文字体, 所以无法识别部分生僻字, 经典例子是日系动物园和 "鲃鱼", 这里推荐把 "鲃鱼" 改名为 "肥鱼", 以解决相关问题, 以后会解决这个问题**

## 未来开发任务

任务大致按优先级排序。 
- 浴场修复，任务调度系统（对轮换策略的支持）
- 更完善的舰船解装逻辑。
- 舰船掉落数据统计。
- 建造，开发，强化，装备废弃等更多功能
- 船舱扫描检查。
- 舰船更换装备。
