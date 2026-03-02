"""最小示例 — 刷战役 (困难航母)。

执行 3 次困难航母战役。
"""

from autowsgr.ops import CampaignRunner
from autowsgr.scheduler import launch


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
