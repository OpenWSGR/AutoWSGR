from autowsgr.fight.event.event_2023_0809 import EventFightPlan20230809
from autowsgr.scripts.main import start_script

timer = start_script()
plan = EventFightPlan20230809(timer, "event/20230809/E10AD.yaml", fleet_id=4)
plan.run_for_times(500)  # 第一个参数是战斗次数,还有个可选参数为检查远征时间，默认为1800S
