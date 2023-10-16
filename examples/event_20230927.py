from autowsgr.fight.event.event_2023_0927 import EventFightPlan20230927
from autowsgr.scripts.main import start_script

timer = start_script()
plan = EventFightPlan20230927(timer, "event/20230927/E10AD.yaml", fleet_id=2)
plan.run_for_times(400)  # 第一个参数是战斗次数,还有个可选参数为检查远征时间，默认为1800S
