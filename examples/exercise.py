import AutoWSGR.fight.exercise as ef
from AutoWSGR.scripts.main import start_script

timer = start_script(settings_path=None)
exf = ef.NormalExercisePlan(timer, "exercise/plan_1.yaml")
exf.run()
