import os
from os.path import dirname, join

import autowsgr.fight.battle as bf
import autowsgr.fight.decisive_battle as df
import autowsgr.fight.exercise as ef
import autowsgr.fight.normal_fight as nf
import autowsgr.scripts.daily_api as da
from autowsgr.game.game_operation import build, cook
from autowsgr.scripts.main import start_script

# 完成周常1-9图任务(针对作者的船舱),可以在plans/week中修改每个图出击的编队
timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")


def week(start=1, start_times=0, fleet_id=2, change=True):
    changes = [None, -1, None, -1, -1, None, None, None, None, -1]
    last_point = [None, "B", "F", "G", "L", "I", "J", "M", "L", "O"]
    result = ["S"] * 9 + ["A"]
    if change:
        changes[start] = -1
    for i in range(start, 10):
        plan = nf.NormalFightPlan(timer, f"week/{i}.yaml", fleet_id, changes[i])
        if i == start:
            plan.run_for_times_condition(5 - start_times, last_point[i], result[i])
        else:
            plan.run_for_times_condition(5, last_point[i], result[i])



operation = da.DailyOperation(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings/user_settings.yaml")
operation.run()
