import os
import time

from autowsgr.game.build import BuildManager
from autowsgr.scripts.main import start_script

resources = [90, 30, 90, 30]

timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
build_manager = BuildManager(timer)

while build_manager.has_empty_slot():
    build_manager.build(resources=resources)
    print(build_manager.slot_eta)


while True:
    time.sleep(build_manager.get_timedelta().total_seconds())
    build_manager.build(resources=resources)
    print(build_manager.slot_eta)
