from autowsgr.fight.event.event_2025_0123 import EventFightPlan20250123
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')
# set_support(timer,True) # 如果要在战斗前开启战役支援请取消这一行的注释
plan = EventFightPlan20250123(
    timer,
    plan_path='H1AB炸鱼',
    fleet_id=4,
)
# plan_path处可填写plan的yaml文件的绝对地址, 也可使用相对地址直接填写plan的文件名
# 详细的plan名可在data/plans/event/20250123查看，fleet_id为出击编队


plan.run_for_times(
    500,
)  # 第一个参数是战斗次数,还有个可选参数为检查远征时间，默认为1800S
