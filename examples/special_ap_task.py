import autowsgr.fight.normal_fight as nf
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')


# 战利品限时任务
def special_ap_task(fleet_id=4):
    # 战利品限时任务大多情况下，都是第 6,7 章的规则
    # 对当前活动的解注释
    plans = [
        {'path': '6-1', 'last_point': 'E', 'result': 'B'},
        {'path': '6-2', 'last_point': 'J', 'result': 'B'},
        # {'path': '6-4D', 'last_point': 'D', 'result': 'B'},
        # {'path': '6-4F', 'last_point': 'F', 'result': 'B'},
        {'path': '7-1', 'last_point': 'F', 'result': 'B'},
        # {'path': '7-2', 'last_point': 'L', 'result': 'B'},
        # {'path': '7-3', 'last_point': 'H', 'result': 'B'},
        {'path': '7-4', 'last_point': 'D', 'result': 'A'},
        {'path': '7-5', 'last_point': 'G', 'result': 'S'},
    ]

    for plan in plans:
        fight = nf.NormalFightPlan(
            timer=timer,
            plan_path=timer.plan_tree['special_ap_task'][plan['path']],
            fleet_id=fleet_id,
            fleet=-1,
        )

        fight.run_for_times_condition(
            times=1,
            last_point=plan['last_point'],
            result=plan['result'],
        )


special_ap_task()
