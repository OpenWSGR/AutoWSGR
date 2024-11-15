import time

from autowsgr.fight.normal_fight import NormalFightPlan
from autowsgr.game.build import BuildManager
from autowsgr.game.game_operation import cook
from autowsgr.scripts.daily_api import DailyOperation
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')


def week(start=1, start_times=0, fleet_id=4, change=True):
    # 完成周常任务(针对作者的船舱)
    changes = [None, -1, -1, -1, -1, None, None, None, None, -1]
    last_point = [None, 'B', 'F', 'G', 'L', 'I', 'J', 'M', 'L', 'O']
    result = [None] + ['S'] * 8
    if change:
        changes[start] = -1
    for i in range(start, 10):
        plan = NormalFightPlan(
            timer,
            timer.plan_tree['week'][i],
            fleet_id,
            changes[i],
        )
        if i == start:
            plan.run_for_times_condition(5 - start_times, last_point[i], result[i])
        else:
            plan.run_for_times_condition(5, last_point[i], result[i])


def day():
    # 完成日常建造, 开发, 做菜任务
    cook(timer, 3, force_click=False)
    resources = [90, 30, 90, 30]
    equipment_resources = [10, 90, 90, 30]
    build_manager = BuildManager(timer)

    build_manager.build(resources=resources)
    print(build_manager.slot_eta)

    for _ in range(3):
        build_manager.build(type='equipment', resources=equipment_resources)
        print(build_manager.slot_eta)
        print(build_manager.get_timedelta(type='equipment').total_seconds())
        time.sleep(build_manager.get_timedelta(type='equipment').total_seconds())


week()

# 日常，可以实现日常出击，战役，演习等操作
operation = DailyOperation(timer)
operation.run()
