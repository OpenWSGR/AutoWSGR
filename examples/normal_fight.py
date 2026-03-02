"""最小示例 — 常规作战 (7-4 千伪)。

使用内置策略 ``7-4千伪`` 执行 3 次常规作战。
策略文件自动从 ``autowsgr/data/plan/normal_fight/`` 解析，无需指定完整路径。
"""

from autowsgr.ops import run_normal_fight_from_yaml
from autowsgr.scheduler import launch


# 1. 启动 (加载配置 → 连接模拟器 → 启动游戏)
ctx = launch('usersettings.yaml')

# 2. 执行常规战 — 只需传策略名称，自动在包数据目录中查找
results = run_normal_fight_from_yaml(ctx, '7-4千伪', times=3)

print(f'完成 {len(results)} 次常规战')
