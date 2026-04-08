"""最小示例 — 刷决战 (第 6 章)。

执行 1 轮完整决战 (3 个小关)。
需根据自己的舰船配置修改 level1 / level2 / flagship_priority。
"""

from autowsgr.infra import DecisiveConfig
from autowsgr.ops import DecisiveController
from autowsgr.scheduler import launch


"""
U-1206
U-96
U-47
鹦鹉螺
鲃鱼
伊-25

M-296
大青花鱼
U-1405
射水鱼
"""


# 1. 启动
ctx = launch('usersettings.yaml')

# 2. 配置决战参数
config = DecisiveConfig(
    chapter=6,
    decisive_rounds=3,
    level1=['U-1206', 'U-96', 'U-47', '鹦鹉螺', '鲃鱼', '伊-25'],
    level2=['M-296', '大青花鱼', 'U-1405', '射水鱼'],
    flagship_priority=['U-1206'],
)

controller = DecisiveController(ctx, config)
results = controller.run_for_times(config.decisive_rounds)

print(f'决战结果: {[r.value for r in results]}')
