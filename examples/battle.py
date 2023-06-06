import AutoWSGR.fight.battle as bf
from AutoWSGR.scripts.main import start_script

timer = start_script()
baf = bf.BattlePlan(timer, "battle/困难驱逐.yaml")
baf.run()

