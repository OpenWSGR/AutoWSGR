import sys

from autowsgr.fight import DecisiveBattle
from autowsgr.scripts.main import start_script


run_times = int(sys.argv[1])

print('=' * 20)
print('决战脚本启动')
print(f'战斗次数: {run_times}')
print('=' * 20)

timer = start_script('./user_settings.yaml')

decisive_battle = DecisiveBattle(timer)
decisive_battle.run_for_times(run_times)
