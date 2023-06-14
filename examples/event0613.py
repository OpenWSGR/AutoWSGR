from AutoWSGR.fight.event.event_2023_0613 import EventFightPlan20230613
from AutoWSGR.scripts.main import start_script

timer = start_script()
plan = EventFightPlan20230613(timer, "event/20230613/E10D.yaml", fleet_id=3)
plan.run_for_times(100)
