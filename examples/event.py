from autowsgr.fight.event.event_2023_1215 import EventFightPlan20231215
from autowsgr.scripts.main import start_script

#活动自动化
timer = start_script()
plan = EventFightPlan20231215(timer, "event/20231215/E10AG.yaml", fleet_id=2)
plan.run_for_times(500)  # 第一个参数是战斗次数,还有个可选参数为检查远征时间，默认为1800S
