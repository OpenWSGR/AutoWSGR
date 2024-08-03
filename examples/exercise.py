import os

import autowsgr.fight.exercise as ef
from autowsgr.scripts.main import start_script

timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
exf = ef.NormalExercisePlan(timer, "exercise/plan_1.yaml")
exf.run()
