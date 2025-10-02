from autowsgr.scripts.daily_api import DailyOperation
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')

# 日常，可以实现日常出击，战役，演习等操作
operation = DailyOperation(timer)
operation.run()
