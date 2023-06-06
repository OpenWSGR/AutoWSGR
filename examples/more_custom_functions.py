import AutoWSGR.fight.normal_fight as nf
import AutoWSGR.fight.decisive_battle as df
import AutoWSGR.fight.battle as bf
import AutoWSGR.fight.exercise as ef
import AutoWSGR.scripts.daily_api as da

import os

from AutoWSGR.game.game_operation import cook, build
from AutoWSGR.scripts.main import start_script
from os.path import dirname
from os.path import join 
from AutoWSGR.game.game_operation import build

my_df_level1 = ["肥鱼", "U-1206", "狼群47", "射水鱼", "U-96", "U-1405"]
my_df_level2 = ["U-81", "大青花鱼"]
my_df_fs = ["U-1405", "U-47", "U-96", "U-1206"]

timer = start_script(join(dirname(__file__), "user_settings", "user_settings.yaml"))
exf = ef.NormalExercisePlan(timer, "exercise/plan_1.yaml")
baf = bf.BattlePlan(timer, "battle/困难巡洋.yaml")
dcf6 = df.DecisiveBattle(timer, 6, 1, 'A', level1=my_df_level1, level2=my_df_level2, flagship_priority=my_df_fs)
dcf4 = df.DecisiveBattle(timer, 4, 1, 'A', level1=my_df_level1, level2=my_df_level2, flagship_priority=my_df_fs)
nf741 = nf.NormalFightPlan(timer, "normal_fight/7-46SS-all.yaml", fleet_id=2, fleet=None)
nf742 = nf.NormalFightPlan(timer, "week/7.yaml", fleet_id=2, fleet=None)
nf91 = nf.NormalFightPlan(timer, "normal_fight/9-1A.yaml", fleet_id=4, fleet=None)
nf92 = nf.NormalFightPlan(timer, "week/9.yaml", fleet_id=3, fleet=None)
nf81 = nf.NormalFightPlan(timer, "normal_fight/8-1A.yaml", fleet_id=3, fleet=None)

def week(start=1, start_times=0, fleet_id=2, change=True):
    # 完成周常任务(针对作者的船舱)
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


def day():
    # 完成日常建造, 开发, 做菜任务
    cook(timer, 1)
    build(timer, "ship", [120, 30, 120, 30])
    for i in range(3):
        build(timer, "equipment", [10, 90, 90, 30])


operation = da.DailyOperation(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings/user_settings.yaml")
operation.run()
