<div align=center>
<img src="https://raw.githubusercontent.com/huan-yp/Auto-WSGR/main/.assets/logo.png">
</div>

## 项目简介

![](https://img.shields.io/github/repo-size/huan-yp/Auto-WSGR) ![](https://img.shields.io/pypi/v/AutoWSGR) ![](https://img.shields.io/pypi/dm/AutoWSGR) ![](https://img.shields.io/github/issues/huan-yp/Auto-WSGR) ![MIT licensed](https://img.shields.io/badge/license-MIT-brightgreen.svg)

用 python 与 c++ 实现的 战舰少女R 的自动化流水线 & 数据统计一体化脚本, 提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口.

参与开发、用户交流、闲聊： qq群 568500514

## 近期更新

- 支持当前活动 "深寒危机", 详细信息见文档 *2023/6/14*
- 设置文件格式有小幅度调整, `dock_full_destroy` 参数位置发生了改变, 请对比自己的文件和默认文件. - *2023/6/9*
- 支持开发, 建造, 用餐功能 *2023/4/26*
- GUI上线测试，详情请见：[AutoWSGR-GUI](https://github.com/Nickydusk/AutoWSGR-GUI) - *2023/2/26*
![image-20230226001532677](/.assets/GUI.png)

## 使用本项目

现已支持远征、修理、解装等基础操作，以及常规战、决战、活动等自动战斗。有简单易用封装的日常挂机脚本，也可以自己组合基础操作实现自定义脚本。

安装使用与详细功能请见：[中文文档](/documentation/%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.md)

## 参与开发

欢迎热爱“战舰少女R”以及有一定python基础的同学加入开发，共同完善这个项目。您可以实现新的功能，也可以改进现有功能，或者修复bug。如果您有好的想法，也可以提出issue或加qq群讨论。

本项目已设置好pre-commit进行代码格式化，请在commit前执行以下操作以启用该功能：
```
pre-commit install
```

未来开发任务大致按优先级排序：
- 资源、舰船掉落数据统计。
- 任务调度系统（对轮换策略的支持）
- 更完善的舰船解装逻辑。
- 强化，装备废弃等更多功能
- 船舱扫描检查。
- 舰船更换装备。
