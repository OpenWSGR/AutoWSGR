"""最小示例 — 刷决战 (第 6 章)。

执行 1 轮完整决战 (3 个小关)。
需根据自己的舰船配置修改 level1 / level2 / flagship_priority。
"""

from autowsgr.infra import DecisiveConfig
from autowsgr.ops import DecisiveController
from autowsgr.scheduler import launch


# 1. 启动
ctx = launch('usersettings.yaml')

# 2. 配置决战参数
config = DecisiveConfig(
    chapter=6,
    level1=['U-1206', 'U-96', 'U-47', '鹦鹉螺', '鲃鱼', '伊-25'],
    level2=['M-296', '大青花鱼', 'U-1405'],
    flagship_priority=['U-1206'],
)

controller = DecisiveController(ctx, config)
result = controller.run()

print(f'决战结果: {result.value}')
