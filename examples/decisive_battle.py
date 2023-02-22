import os

from AutoWSGR.fight import DecisiveBattle
from AutoWSGR.scripts.main import start_script

timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml", to_main_page=False)

decisive_battle = DecisiveBattle(timer, 6, 1, 'A', level1=["肥鱼", "U-1206", "U-47", "射水鱼", "U-96", "U-1405"],
                                 level2=["U-81", "大青花鱼"], flagship_priority=["U-1405", "U-47"])
decisive_battle.start_fight()
# for _ in range(6):
#     decisive_battle.reset()
#     decisive_battle.start_fight()
