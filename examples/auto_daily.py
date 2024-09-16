import os

from autowsgr.scripts.daily_api import DailyOperation

# 日常，可以实现日常出击，战役，演习等操作
operation = DailyOperation(
    f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml"
)
operation.run()
