import sys

from autowsgr.fight.event.event_2025_0710 import EventFightPlan20250710
from autowsgr.scripts.main import start_script


plan_path = sys.argv[1]
fleet_id = int(sys.argv[2])
battle_count = int(sys.argv[3])

print('=' * 20)
print('活动脚本启动')
print(f'Plan 路径: {plan_path}')
print(f'出征舰队: {fleet_id}')
print(f'战斗次数: {battle_count}')
print('=' * 20)

timer = start_script('./user_settings.yaml')

plan = EventFightPlan20250710(
    timer,
    plan_path=plan_path,
    fleet_id=fleet_id,
)

plan.run_for_times(battle_count)
