"""最小示例 — 常规作战 (9-2 胖次 85BOSS)。

使用 ``run_yaml_plan`` 执行常规作战
策略文件自动从 ``autowsgr/data/plan/normal_fight/`` 解析，无需指定完整路径。
"""

from autowsgr.scheduler import launch, run_yaml_plan


# 1. 启动 (加载配置 → 连接模拟器 → 启动游戏)
ctx = launch('usersettings.yaml')

# 2. 执行常规战 — 只需传策略名称，自动在包数据目录中查找
results = run_yaml_plan(ctx, '9-2速刷胖次', times=10, fleet_id=3)
print(f'完成 {len(results)} 次常规战')
