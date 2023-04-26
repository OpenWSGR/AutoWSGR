from AutoWSGR.scripts.main import start_script
from AutoWSGR.game.game_operation import build

timer = start_script()
build(timer, "ship", [120, 30, 120, 30], force=True)
for i in range(3):
    build(timer, "equipment", [10, 10, 10, 10])
