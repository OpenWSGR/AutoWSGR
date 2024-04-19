import os

import autowsgr.fight.exercise as ef
from autowsgr.fight.event.event_2024_0419 import EventFightPlan20240419
from autowsgr.game.game_operation import SetSupport
from autowsgr.ocr.digit import get_loot_and_ship
from autowsgr.scripts.daily_api import DailyOperation
from autowsgr.scripts.main import start_script

timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
# SetSupport(timer,True) # 如果要在战斗前开启战役支援请取消这一行的注释
plan = EventFightPlan20240419(timer, "event/20240419/E11CD.yaml", fleet_id=4)
plan.run_for_times(500)  # 第一个参数是战斗次数,还有个可选参数为检查远征时间，默认为1800S


operation = DailyOperation(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
operation.run()
