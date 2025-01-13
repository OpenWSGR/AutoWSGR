from autowsgr.fight.exercise import NormalExercisePlan
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')
exf = NormalExercisePlan(timer, plan_path='plan_1', fleet_id=2)  # 修改 fleet_id 为演习出征舰队编号
exf.run()
