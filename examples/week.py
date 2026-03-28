import sys

from autowsgr.ops.normal_fight import NormalFightRunner, get_normal_fight_plan
from autowsgr.scheduler import launch


# run_for_times_condition的运行示例
last_point = [None, 'A', 'F', 'I', 'I', 'I', 'J', 'M', 'L', 'O']
i = int(float(sys.argv[1]))
ctx = launch('./usersettings.yaml')
# 这里修改为你自己的计划路径即可
plan = get_normal_fight_plan('./week/' + sys.argv[1] + '.yaml')
runner = NormalFightRunner(
    ctx,
    plan,
    fleet_id=2,
)
runner.run_for_times_condition(1, last_point[i])
