"""最小示例 — 修改舰队。

修改第 2 舰队的舰船配置。
"""

from autowsgr.ops import goto_page
from autowsgr.scheduler import launch
from autowsgr.ui import BattlePreparationPage, PageName


# 1. 启动 (加载配置 → 连接模拟器 → 启动游戏)
ctx = launch('usersettings.yaml')

goto_page(ctx, PageName.BATTLE_PREP)

page = BattlePreparationPage(ctx)

page.change_fleet(2, ['U-47', 'U-96'])
