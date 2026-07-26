"""auto_daily — 全天挂机 (战役 + 演习 + 远征 + 常规战)。

读取配置文件的 ``daily_automation`` 段, 用「触发器 + 优先级队列」调度器持续挂机,
支持跨日自动重置 (0 点刷新战役次数 / 演习时段 / 当日掉落上限)。

优先级: 远征(0) < 战役(5) < 演习(10) < 常规战(100, 空闲填充)。

用法::

    # 默认查找当前目录下的 user_settings.yaml / usersettings.yaml
    python examples/auto_daily.py

    # 显式指定配置 (推荐, 用户常用文件名带下划线)
    python examples/auto_daily.py --config D:/Games/autowsgr/old/user_settings.yaml

停止:
    - 第一次 Ctrl+C → 设置停止信号, 等当前战斗结束后优雅退出。
    - 第二次 Ctrl+C → 强制退出 (KeyboardInterrupt)。
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from autowsgr.scheduler import TaskScheduler, build_daily_plan, launch


# 默认查找的配置文件名 (兼容带/不带下划线两种写法)
_DEFAULT_CONFIG_CANDIDATES = (
    'user_settings.yaml',
    'usersettings.yaml',
)


def _resolve_config(path: str | None) -> str | None:
    """解析配置文件路径; 未指定时按候选名在当前目录查找。"""
    if path:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f'配置文件不存在: {path}')
        return str(p)
    for name in _DEFAULT_CONFIG_CANDIDATES:
        if Path(name).is_file():
            return name
    return None  # 交由 launch() 自动检测或使用默认值


def main() -> int:
    parser = argparse.ArgumentParser(
        description='auto_daily 全天挂机 (战役+演习+远征+常规战)',
    )
    parser.add_argument(
        '--config',
        '-c',
        help='配置文件路径 (YAML); 未指定则查找 user_settings.yaml / usersettings.yaml',
    )
    parser.add_argument(
        '--expedition-interval',
        type=float,
        default=600.0,
        help='远征轮询间隔 (秒), 默认 600',
    )
    parser.add_argument(
        '--idle-sleep',
        type=float,
        default=5.0,
        help='队列空闲时的挂机轮询间隔 (秒), 默认 5',
    )
    args = parser.parse_args()

    config_path = _resolve_config(args.config)
    if config_path is None:
        print(
            '[auto_daily] 未找到配置文件, 将使用默认值 '
            '(daily_automation 可能为空 → 不挂机)。'
            '可用 --config 指定。',
            file=sys.stderr,
        )

    # 1. 启动: 加载配置 → 连接模拟器 → 启动游戏 → 返回就绪 ctx
    ctx = launch(config_path)

    if ctx.config.daily_automation is None:
        print(
            '[auto_daily] 配置中无 daily_automation 段, 退出。'
            '请在配置文件中添加 daily_automation 设置。',
            file=sys.stderr,
        )
        return 1

    # 2. Ctrl+C → 优雅停止 (第一次) / 强制退出 (第二次)
    def _on_stop(signum: int, frame: object) -> None:  # noqa: ARG001
        if ctx.stop_event.is_set():
            print('\n[auto_daily] 再次收到停止信号, 强制退出。', file=sys.stderr)
            raise KeyboardInterrupt
        print('\n[auto_daily] 收到停止信号, 等当前任务结束后退出...', file=sys.stderr)
        ctx.stop_event.set()

    signal.signal(signal.SIGINT, _on_stop)
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, _on_stop)

    # 3. 构建日常计划: 把 daily_automation 翻译成触发器
    #    expedition_interval=0: 关闭旧的顺序远征检查, 交给远征触发器
    scheduler = TaskScheduler(ctx, expedition_interval=0, idle_sleep=args.idle_sleep)
    build_daily_plan(scheduler, ctx, expedition_interval=args.expedition_interval)

    # 4. 触发器调度主循环 (持续挂机, 直到 stop_event)
    scheduler.run_daily()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
