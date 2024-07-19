<div align=center>
<img src="https://raw.githubusercontent.com/huan-yp/Auto-WSGR/main/.assets/logo.png">
</div>

## 项目简介

![](https://img.shields.io/github/repo-size/huan-yp/Auto-WSGR) ![](https://img.shields.io/pypi/v/autowsgr) ![](https://img.shields.io/pypi/dm/autowsgr) ![](https://img.shields.io/github/issues/huan-yp/Auto-WSGR) ![MIT licensed](https://img.shields.io/badge/license-MIT-brightgreen.svg)

用 python 与 c++ 实现的 战舰少女R 的自动化流水线 & 数据统计一体化脚本, 提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口.

参与开发、用户交流、闲聊： qq群 568500514

## 近期更新
- 删除配置`PLAN_ROOT`和`SHIP_NAME_PATH`,将会默认从example文件夹下加载`PLAN`文件和`SHIP_NAME`文件,请重新从`GitHub`下载`example文件夹`，并注意自己的配置.  **2024/07/19**
- 获取舰船现在会基于图像识别返回 [舰船名，舰船类型].  **2024/07/18**
- 添加自动检查更新的功能，设置文件格式小幅度更新，请重新下载`example`文件夹下`user_settings.yaml`,如果想关闭自动更新请设置`check_update`参数为`False`,请对比自己的文件和默认文件.  **2024/04/19**
- 支持当前活动 "舰队问答-黄金风笛", 详细信息见[文档](/documentation/舰队问答类型活动.md)  **2024/04/19**
- 添加日常出击任务中500船停止出击的功能  **2024/04/11**

## 使用本项目

现已支持远征、修理、解装等基础操作，以及常规战、决战、活动等自动战斗。有简单易用封装的日常挂机脚本，也可以自己组合基础操作实现自定义脚本。

安装使用与详细功能请见：[中文文档](/documentation/%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.md) 或 简易图文教程[notion文档](https://sincere-theater-0e6.notion.site/56a26bfe32da4931a6a1ece332173211?v=428430662def42a2a7ea6dac48238d50)


## 参与开发

欢迎热爱“战舰少女R”以及有一定python基础的同学加入开发，共同完善这个项目。您可以实现新的功能，也可以改进现有功能，或者修复bug。如果您有好的想法，也可以提出issue或加qq群讨论。

本项目已设置好poetry进行版本管理，pre-commit进行代码格式化。开发者请**不要用pip安装autowsgr**，改为执行以下命令以开发模式在本地安装（全程需要代理）：
```
git clone https://github.com/huan-yp/Auto-WSGR
cd Auto-WSGR
./develop_install.bat
```

非常感谢我们所有的贡献者！如果你想贡献代码，欢迎发起一个Pull Request或创建一个Issue

<a href="https://github.com/huan-yp/Auto-WSGR/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=huan-yp/Auto-WSGR" />
</a>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=huan-yp/Auto-WSGR&type=Date)](https://star-history.com/#huan-yp/Auto-WSGR&Date)
