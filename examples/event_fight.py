"""最小示例 — 活动作战 (E5ADE 夜战)。

使用内置策略 ``E5ADE夜战`` 执行 5 次活动战斗。
策略文件自动从 ``autowsgr/data/plan/event/`` 解析，无需指定完整路径。
"""

from autowsgr.ops import run_event_fight_from_yaml
from autowsgr.scheduler import launch


# 1. 启动
ctx = launch('usersettings.yaml')

# 2. 执行活动战 — 只需传策略名称, 支持外部指定舰队
results = run_event_fight_from_yaml(ctx, 'E5ADE夜战', times=5, fleet_id=2)

print(f'完成 {len(results)} 次活动战')
