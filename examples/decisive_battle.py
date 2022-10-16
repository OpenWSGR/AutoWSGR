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


timer = start_script('user_settings.yaml', to_main_page=False)
show_all_debug_info()

decisive_battle = DecisiveBattle(timer, 6, 1, 'A', level1=["鲃鱼", "U-1206", "U-47", "射水鱼", "U-96", "U-1405"], \
    level2=["U-81", "大青花鱼"], flagship_priority=["U-1405", "U-47"])
decisive_battle.start_fight()
for i in range(2):
    decisive_battle.reset()
    decisive_battle.start_fight()
    

