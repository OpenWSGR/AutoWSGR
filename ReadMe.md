## AutoWSGR

![](https://img.shields.io/github/repo-size/huan-yp/Auto-WSGR) ![](https://img.shields.io/pypi/v/AutoWSGR) ![](https://img.shields.io/pypi/dm/AutoWSGR) ![](https://img.shields.io/github/issues/huan-yp/Auto-WSGR) ![MIT licensed](https://img.shields.io/badge/license-MIT-brightgreen.svg)

用 python 与 c++ 实现的 战舰少女R 的自动化流水线 & 数据统计一体化脚本, 提供 `WSGR` 游戏级别接口以及部分图像和原子操作接口.

用户交流, 意见反馈 qq 群: 568500514

## 近期更新

![image-20230226001532677](assets/image-20230226001532677.png)
- 支持开发, 建造, 用餐功能 *2023/4/26*
- GUI上线测试，详情请见：[AutoWSGR-GUI](https://github.com/Nickydusk/AutoWSGR-GUI) - *2023/2/26*
- 支持了当前活动 "炽热星辰行动" - *2023/1/20*
- 解装升级为更快的 "一键解装" - *2023/1/12*


## 功能

- 无间断重复远征
- 自动点击完成任务
- 开发, 建造, 用餐
- 全自动出征，可通过简单的描述文本实现高可复用的自定义策略
  - 支持：战役、演习、常规战、决战、除立体强袭外的活动地图
- 支持多种修理模式：快修大破、快修中破、澡堂修理（可指定船名）
- 强容错性
  - 任何游戏界面，返回主页面，处理各种特殊点击需求
  - 游戏卡死、断网时自动重启游戏、模拟器
- `ctrl+alt+c` 终止所有操作并退出程序


## 文档

[中文文档](/documentation/%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.md)


## 未来开发任务

任务大致按优先级排序。 
- 任务调度系统（对轮换策略的支持）
- 更完善的舰船解装逻辑。
- 舰船掉落数据统计。
- 强化，装备废弃等更多功能
- 船舱扫描检查。
- 舰船更换装备。
