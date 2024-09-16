from autowsgr.game.game_operation import cook
from autowsgr.scripts.main import start_script

timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
cook(timer, 1, force_click=False)
