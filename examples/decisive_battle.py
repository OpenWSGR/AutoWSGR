from autowsgr.fight import DecisiveBattle
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')

# 决战出击
decisive_battle = DecisiveBattle(timer)
decisive_battle.run_for_times(1)  # 数字为决战出击的次数
