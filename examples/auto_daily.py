from AutoWSGR.daily_api import DailyOperation

operation = DailyOperation(f"{__file__}/user_settings.yaml")
operation.run()
