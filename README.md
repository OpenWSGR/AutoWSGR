<div align=center>
<img src="https://raw.githubusercontent.com/huan-yp/Auto-WSGR/main/.assets/logo.png">
</div>

## 项目简介

![](https://img.shields.io/github/repo-size/huan-yp/Auto-WSGR) ![](https://img.shields.io/pypi/v/autowsgr) ![](https://img.shields.io/pypi/dm/autowsgr) ![](https://img.shields.io/github/issues/huan-yp/Auto-WSGR) ![MIT licensed](https://img.shields.io/badge/license-MIT-brightgreen.svg)

用 python 与 c++ 实现的 战舰少女R 的自动化流水线 & 数据统计一体化脚本, 提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口.

**如何使用：**[notion文档](https://sincere-theater-0e6.notion.site/56a26bfe32da4931a6a1ece332173211?v=428430662def42a2a7ea6dac48238d50)

参与开发、用户交流、闲聊：qq群 568500514

## 近期更新

- 任务调度支持决战、战役、演习和活动. **2024/10/03**
- 蓝叠模拟器的连接方法改为手动填写adb地址. **2024/10/02**
- 支持当前活动 "征程启航",请重新下载example文件夹中的plans和event.py文件.活动先关的使用方法可以参考[这里](https://sincere-theater-0e6.notion.site/fb9bbe5a4b0a426db59ac7892645ee1b)**2024/09/30**
- 更新到版本1.x.y.z,增加任务调度系统，决战配置参数更新，请对照example中的文件修改自己的参数。**2024/09/26**
- 为简单战役添加plan，现在可以在战役练习战术. **2024/09/03**
- 添加对常规地图9-4的支持,更新ship_name文件,修复决战出征的bug. **2024/08/31**
- 请重新下载`example`文件夹,OCR识别增加新的后端，如果感觉paddleocr速度较慢，可在`user_settings`中设置`OCR_BACKEND`为`easyocr`,增加2-1捞胖次的plan. **2024/08/02**

## 常见报错

如果你在运行本项目时遇到了无法运行的问题，请先在[常见报错](/documentation/FAQ.md)中查找是否有相同案例并尝试按照此方法解决.

## 参与开发

欢迎有一定python基础的同学加入开发，共同完善这个项目。您可以实现新的功能，也可以改进现有功能，或者修复bug。如果您有好的想法，也可以提出issue或加qq群讨论。开发者请**不要用pip安装autowsgr**，改为[本地模式](https://www.notion.so/AutoWSGR-efeb69811b544604b944d5b5727317a4?pvs=4#dc2833ce4b8449ca8293a98f0b2b3b71)安装。


非常感谢我们所有的贡献者！如果你想贡献代码，欢迎发起一个Pull Request或创建一个Issue

<a href="https://github.com/huan-yp/Auto-WSGR/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=huan-yp/Auto-WSGR" />
</a>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=huan-yp/Auto-WSGR&type=Date)](https://star-history.com/#huan-yp/Auto-WSGR&Date)
