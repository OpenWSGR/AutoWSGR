from autowsgr.game.game_operation import cook
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')
cook(timer, 1, force_click=False)
