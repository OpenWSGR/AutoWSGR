<div align=center>
<img src="https://raw.githubusercontent.com/huan-yp/Auto-WSGR/main/.assets/logo.png">
</div>

## 项目简介

![](https://img.shields.io/github/repo-size/huan-yp/Auto-WSGR) ![](https://img.shields.io/pypi/v/autowsgr) ![](https://img.shields.io/pypi/dm/autowsgr) ![](https://img.shields.io/github/issues/huan-yp/Auto-WSGR) ![MIT licensed](https://img.shields.io/badge/license-MIT-brightgreen.svg)

用 python 与 c++ 实现的 战舰少女R 的自动化流水线 & 数据统计一体化脚本, 提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口.

**如何使用：**[用户文档](https://sincere-theater-0e6.notion.site/56a26bfe32da4931a6a1ece332173211?v=428430662def42a2a7ea6dac48238d50)

参与开发、用户交流、闲聊：qq群 568500514

## 近期更新

- 对user_config格式进行升级，请参考examplse/user_config.yaml进行修改. 2024/11/19
- 已弃用 Python 3.9，请升级 Python>=3.10. 2024/10/24
- 计划弃用 `paddleocr` 后端, 请及时修改自己的 `user_settings.yaml` 中`ocr_backend`为`easyocr`. **2024/10/06**
- 任务调度支持决战、战役、演习和活动. **2024/10/03**
- 蓝叠模拟器的连接方法改为手动填写adb地址. **2024/10/02**

## 参与开发

欢迎有一定python基础的同学加入开发，共同完善这个项目。您可以实现新的功能，也可以改进现有功能，或者修复bug。如果您有好的想法，也可以提出issue或加qq群讨论。开发前请仔细阅读 [贡献指南](CONTRIBUTING.md) 和 [用户文档](https://sincere-theater-0e6.notion.site/56a26bfe32da4931a6a1ece332173211?v=428430662def42a2a7ea6dac48238d50)。

注意： 开发者请**不要从pypi安装autowsgr**，改为 [本地模式](https://www.notion.so/AutoWSGR-efeb69811b544604b944d5b5727317a4?pvs=4#dc2833ce4b8449ca8293a98f0b2b3b71) 安装。


非常感谢我们所有的贡献者！如果你想贡献代码，欢迎发起一个Pull Request或创建一个Issue

<a href="https://github.com/huan-yp/Auto-WSGR/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=huan-yp/Auto-WSGR" />
</a>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=huan-yp/Auto-WSGR&type=Date)](https://star-history.com/#huan-yp/Auto-WSGR&Date)
