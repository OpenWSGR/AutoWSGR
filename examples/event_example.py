from AutoWSGR import show_all_debug_info, start_script
from AutoWSGR.fight import NormalExercisePlan
from AutoWSGR.fight.event import EventFightPlan20220928_2

timer = start_script(f"{__file__}/user_settings.yaml")  # 启动模拟器和游戏，得到一个游戏控制器


event_plan2 = EventFightPlan20220928_2(timer, 'plans/event/20220929/E10BB.yaml')
event_plan2.run(same_work=False)
for _ in range(100):
    event_plan2.run(same_work=False)

exercise_plan = NormalExercisePlan(timer, 'plans/exercise/plan_1.yaml')
exercise_plan.run()
