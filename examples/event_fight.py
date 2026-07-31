"""最小示例 — 活动作战 (融合后)。

活动战与常规战已融合: 活动 plan 的 ``chapter`` 写成 E(简单)/H(困难), 入口编码进
``map`` 字段 (``1a``/``1b`` 对应第一/第二入口), 由 ``NormalFightRunner`` 按章节
自动路由到活动地图。本示例用内置活动 plan (H5ADE夜战) 执行 5 次。

策略文件自动从 ``autowsgr/data/plan/event/`` 解析, 无需指定完整路径。
也可把活动 plan 名加入全局配置的 ``normal_fight_tasks``, 由 auto_daily 自动调度
(与常规战共用触发器, 无需为活动单独配置)。
"""

from autowsgr.ops import run_event_fight_from_yaml
from autowsgr.scheduler import launch


# 1. 启动
ctx = launch('usersettings.yaml')

# 2. 执行活动战 — 只需传策略名称, 支持外部指定舰队
results = run_event_fight_from_yaml(ctx, 'H5ADE夜战', times=5, fleet_id=2)

print(f'完成 {len(results)} 次活动战')
