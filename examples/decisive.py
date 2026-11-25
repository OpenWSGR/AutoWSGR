"""最小示例 — 刷决战 (第 6 章)。

每轮执行 1 章（3 个小关）。节点间和等待维修时，调度器会执行配置中已启用的日常任务。
常规战与决战共用舰船，决战期间关闭常规战触发器。
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
