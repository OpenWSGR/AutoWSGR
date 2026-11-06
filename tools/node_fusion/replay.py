"""节点融合标量日志的命令行回放入口，不访问模拟器。"""

from autowsgr.combat.node_fusion.replay import main, replay


__all__ = ['main', 'replay']


if __name__ == '__main__':
    raise SystemExit(main())
