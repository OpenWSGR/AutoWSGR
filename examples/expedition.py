"""最小示例 — 定时收取远征、奖励和浴室维修。

每 5 分钟自动收取一次已完成的远征、任务奖励，并可选择执行浴室维修。
"""

import time

from autowsgr.infra.logger import get_logger
from autowsgr.ops import collect_expedition, collect_rewards, repair_in_bath
from autowsgr.scheduler import launch


_log = get_logger('expedition_example')

# 1. 启动并连接模拟器 (自动检测 usersettings.yaml)
ctx = launch('usersettings.yaml')

# 每 5 分钟运行一次
check_time = 5

# 是否开启自动浴室维修 ( True / False )
# 说明：开启后每次检查都会尝试将修理时间最长的舰船放入浴室。
# 若浴室已满或无舰船需要修理，游戏不会执行操作，脚本可安全运行。
enable_bath_repair = True

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
            _log.info('当前无任务奖励可领取')

        # 浴室维修 (若当前有战斗任务在进行，则跳过，避免占用舰队)
        if enable_bath_repair:
            if getattr(ctx, 'active_fight_tasks', 0) > 0:
                _log.info('检测到当前有战斗任务在进行，跳过浴室维修')
            else:
                try:
                    repair_in_bath(ctx)
                    _log.info('浴室维修检查完成')
                except Exception as e:
                    _log.warning(f'浴室维修执行失败: {e}')

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
