from autowsgr.fight.event.event_2024_0206 import EventFightPlan20240206
from autowsgr.scripts.main import start_script
from autowsgr.ocr.digit import get_loot_and_ship
from autowsgr.game.game_operation import SetSupport
import autowsgr.fight.exercise as ef
from autowsgr.scripts.daily_api import DailyOperation
import os

timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
plan = EventFightPlan20240206(timer, "event/20240206/E10IJ.yaml", fleet_id=3)
plan.run_for_times(500)  # 第一个参数是战斗次数,还有个可选参数为检查远征时间，默认为1800S


operation = DailyOperation(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
operation.run()
