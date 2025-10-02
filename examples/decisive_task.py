# 决战调度功能, 决战过程中可以退出使用浴场修复, 多次决战多次调用 runner.add_decisive_task() 即可

from autowsgr.port.task_runner import TaskRunner
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')
runner = TaskRunner(timer)  # 注册 TaskRunner
runner.add_decisive_task()
runner.run()
