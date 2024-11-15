from autowsgr.fight.exercise import NormalExercisePlan
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')
exf = NormalExercisePlan(timer, 'plan_1')
exf.run()
