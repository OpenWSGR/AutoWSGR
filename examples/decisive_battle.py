from AutoWSGR.constants.settings import show_all_debug_info
from AutoWSGR.fight.decisive_battle import DecisiveBattle
from AutoWSGR.main import start_script

timer = start_script(f"{__file__}/user_settings.yaml", to_main_page=False)
# show_all_debug_info()

decisive_battle = DecisiveBattle(timer, 6, 1, 'A', level1=["肥鱼", "U-1206", "U-47", "射水鱼", "U-96", "U-1405"],
                                 level2=["U-81", "大青花鱼"], flagship_priority=["U-1405", "U-47"])
decisive_battle.start_fight()
# for _ in range(6):
#     decisive_battle.reset()
#     decisive_battle.start_fight()
