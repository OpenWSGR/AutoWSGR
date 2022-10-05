## AutoWSGR

![](https://img.shields.io/github/repo-size/huan-yp/Auto-WSGR) ![](https://img.shields.io/pypi/v/AutoWSGR) ![](https://img.shields.io/pypi/dm/AutoWSGR) ![](https://img.shields.io/github/issues/huan-yp/Auto-WSGR) ![MIT licensed](https://img.shields.io/badge/license-MIT-brightgreen.svg)

用python与c++实现的战舰少女R的自动化流水线 & 数据统计一体化脚本，提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口。

## 近期更新

- 一体化日常挂机策略，使用方式见`examples/auto_daily.py`   \- *2022/10/5*

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

请自行安装 [Python](https://www.python.org/) == 3.7，[雷电模拟器](https://www.ldmnq.com/)，[战舰少女R](http://www.jianniang.com/)

AutoWSGR 目前已支持通过 [PyPI](https://pypi.org/project/AutoWSGR/) 进行部署，您可以通过以下命令一键安装稳定发布版：

```bash
$ pip install AutoWSGR
```

也可以通过以下命令从 GitHub 安装最新版：

```bash
$ pip install git+https://github.com/huan-yp/Auto-WSGR.git@main --upgrade
```

在安装完成后，打开任意命令行并键入：

```python
import AutoWSGR
print(AutoWSGR.__version__)
```

如果没有报错则说明安装成功。

## 快速使用

样例代码在本项目的`examples/`文件夹下，您可以参考使用。计划在未来功能更新稳定后提供全面的中文文档。

为了确保能正确的重启模拟器，建议进行如下设置，否则请确保每次运行前手动打开雷电模拟器：

- 在您的工作目录下新建一个yaml文件（如`user_settings.yaml`），并在其中键入如下设置（替换为您的雷电模拟器安装根目录）

  ```yaml
  LDPLAYER_ROOT: C:\leidian\LDPlayer9
  ```

- 此外请确保雷电模拟器应用程序名为 `dnplayer.exe`，AutoWSGR将使用 `{LDPLAYER_ROOT}\dnplayer.exe` 命令启动模拟器。



## 未来开发任务

舰船精确识别功能。 

活动练级/战术。



