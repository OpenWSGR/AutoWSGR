import time

from AutoWSGR import start_script
from AutoWSGR.constants.settings import S
from AutoWSGR.fight import BattlePlan, NormalExercisePlan, NormalFightPlan
from AutoWSGR.game.game_operation import Expedition, GainBounds, RepairByBath

timer = start_script('user_settings.yaml')
S.DEBUG = False

battle_plan = BattlePlan(timer, plan_path='battle/hard_destroyer.yaml')
fight_plan = NormalFightPlan(timer, plan_path="normal_fight/9-1BF.yaml", fleet_id=3)
expedition_plan = Expedition(timer)
start_time = last_time = time.time()

# 自动战役
ret = "success"
while ret == "success":
    ret = battle_plan.run()

# 自动出征
ret = "success"
while ret == "success":
    ret = fight_plan.run()

    if time.time() - last_time >= 5*60:
        expedition_plan.run(True)
        GainBounds(timer)
        last_time = time.time()

# 自动远征
while True:
    RepairByBath(timer)
    expedition_plan.run(True)
    GainBounds(timer)
    time.sleep(360)
