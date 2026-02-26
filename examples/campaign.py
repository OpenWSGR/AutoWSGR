"""最小示例 — 刷战役 (困难航母)。

执行 3 次困难航母战役，复纵阵型，开启夜战。
"""

from autowsgr.scheduler import launch
from autowsgr.ops import CampaignRunner

# 1. 启动
ctx = launch('usersettings.yaml')

# 2. 执行战役
runner = CampaignRunner(
    ctx,
    campaign_name='困难航母',
    times=3,
)
results = runner.run()

print(f'完成 {len(results)} 次战役')
