import os

import autowsgr.fight.battle as bf
from autowsgr.scripts.main import start_script

# 实现战役的出击
timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
baf = bf.BattlePlan(timer, "battle/困难驱逐.yaml")
baf.run()
