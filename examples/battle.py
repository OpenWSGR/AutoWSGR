from autowsgr.fight.battle import BattlePlan
from autowsgr.scripts.main import start_script


# 实现战役的出击
timer = start_script('./user_settings.yaml')
baf = BattlePlan(timer, '困难驱逐')
baf.run()
