"""最小示例 — 定时收取远征和奖励。

每 5 分钟自动收取一次已完成的远征和任务奖励。
"""

import time

from autowsgr.infra.logger import get_logger
from autowsgr.ops import collect_expedition, collect_rewards
from autowsgr.scheduler import launch


_log = get_logger('expedition_example')

# 1. 启动并连接模拟器 (自动检测 usersettings.yaml)
ctx = launch('usersettings.yaml')

# 每 5 分钟运行一次
check_time = 5

_log.info(f'定时任务已启动，每 {check_time} 分钟执行一次收取操作')

while True:
    try:
        # 记录开始时间
        start_time = time.time()

        _log.info('--- 开始例行检查 ---')

        # 收取远征 (自动重新派遣)
        if collect_expedition(ctx):
            _log.info('成功收取远征并重新派遣')
        else:
            _log.info('当前无远征可收取')

        # 收取任务奖励
        if collect_rewards(ctx):
            _log.info('成功收取任务奖励')
        else:
            _log.info('当前无任务奖励可收取')

        # 计算剩余等待时间
        elapsed = time.time() - start_time
        wait_time = max(1, check_time * 60 - elapsed)

        _log.info(f'检查完毕，等待 {wait_time / 60:.0f} 分钟后进行下一次检查...')
        time.sleep(wait_time)

    except KeyboardInterrupt:
        _log.info('用户手动停止脚本')
        break
    except Exception as e:
        _log.error(f'执行过程中出现异常: {e}')
        _log.info('等待 1 分钟后重试...')
        time.sleep(60)
