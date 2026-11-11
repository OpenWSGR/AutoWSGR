"""节点融合标量日志的命令行回放入口，不访问模拟器；gzip 日志透明解压。"""

from __future__ import annotations

import gzip
import sys
import tempfile
from pathlib import Path

from autowsgr.combat.node_fusion.replay import main as _plain_main
from autowsgr.combat.node_fusion.replay import replay


__all__ = ['main', 'replay']


def main(argv: list[str] | None = None) -> int:
    """命令行入口：gzip 日志先解压成临时明文，再原样转交参数。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and not args[0].startswith('-'):
        source = Path(args[0])
        data = source.read_bytes()
        if data[:2] == b'\x1f\x8b':
            with tempfile.NamedTemporaryFile(
                'wb', suffix='.jsonl', delete=False, dir=source.parent
            ) as temp:
                temp.write(gzip.decompress(data))
                plain = Path(temp.name)
            try:
                args[0] = str(plain)
                return _plain_main(args)
            finally:
                plain.unlink(missing_ok=True)
    return _plain_main(args)


if __name__ == '__main__':
    raise SystemExit(main())
