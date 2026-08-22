"""周常任务示例 — 触发器模式 (一次性计划出击)。

使用 ``run_yaml_plan`` 执行指定周常图:
条件判定 (结束节点 + 评级) 由 YAML的 ``node_args`` 配置,
不达标场次不计入次数并自动重打, 全部达标后自动退出。
计划文件在包数据目录中查找 (如 ``1周常.yaml``)。
"""

import sys

from autowsgr.scheduler import launch, run_yaml_plan


# 1. 启动 (加载配置 → 连接模拟器 → 启动游戏)
ctx = launch('./usersettings.full.yaml')

# 2. 执行常规战 — 周常图, 按章节编号拼接策略名 (如 1 → 1周常)
results = run_yaml_plan(ctx, sys.argv[1] + '周常', times=1, fleet_id=2)
print(f'完成 {len(results)} 次常规战')
