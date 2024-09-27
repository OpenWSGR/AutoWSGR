import os

from autowsgr.port.task_runner import FightTask, TaskRunner
from autowsgr.scripts.main import start_script

timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")

runner = TaskRunner()  # 注册 TaskRunner
runner.tasks.append(
    FightTask(
        timer,
        file_path=r"C:\Users\huany\Desktop\Projects\Auto-WSGR-dev\Auto-WSGR\examples\fight_task_example.yaml",  # 任务配置文件路径，这个地方填写自己写好的配置文件
    )
)  # 添加任务 (仅支持绝对路径)
runner.run()  # 启动调度器
