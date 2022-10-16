import time

from AutoWSGR.main import start_script
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.settings import S, show_all_debug_info
from AutoWSGR.fight.battle import BattlePlan
from AutoWSGR.fight.normal_fight import NormalFightPlan
from AutoWSGR.fight.exercise import NormalExercisePlan
from AutoWSGR.fight.decisive_battle import DecisiveBattle
from AutoWSGR.fight.event.event_2022_0928 import EventFightPlan20220928
from AutoWSGR.game.game_operation import Expedition, GainBounds, RepairByBath
from AutoWSGR.port.ship import Fleet


timer = start_script('user_settings.yaml', to_main_page=False)
show_all_debug_info()
fleet = Fleet(timer)
fleet.set_ship(["", "U-1405", "狼群47", "U-81", "大青花鱼"], search_method=None)
quit()
decisive_battle = DecisiveBattle(timer, 6, 1, 'D', level1=["肥鱼", "U-1206", "狼群47", "射水鱼", "U-96", "U-1405"], \
    level2=["U-81", "大青花鱼"], flagship_priority=["U-1405", "狼群47"])
# decisive_battle.start_fight()
battle_plan = BattlePlan(timer, plan_path='battle/hard_Cruiser.yaml')
fight_plan = NormalFightPlan(timer, plan_path="normal_fight/9-1BF.yaml", fleet_id=3)
fight_plan = EventFightPlan20220928(timer, plan_path='event/20220929/E10AE.yaml', fleet_id=2)
exercise_plan = NormalExercisePlan(timer, plan_path='exercise/plan_1.yaml')
expedition_plan = Expedition(timer)
start_time = last_time = time.time()
# exercise_plan.run()
event_plan = EventFightPlan20220928(timer, 'event/20220929/E10AE.yaml', 2)
for i in range(60):
    event_plan.run()
# 自动出征
"""ret = fight_plan.run()
while ret == "success":
    ret = fight_plan.run(same_work=True)
    if time.time() - last_time >= 900:
        expedition_plan.run(True)
        GainBounds(timer)
        last_time = time.time()"""

# 自动远征
"""exercise_plan = NormalExercisePlan(timer, 'exercise/plan_1.yaml')
exercise_plan.run()"""
while True:
    RepairByBath(timer)
    expedition_plan.run(True)
    GainBounds(timer)
    time.sleep(360)
