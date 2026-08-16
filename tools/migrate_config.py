"""classic 老版本配置迁移工具 — 生成新版配置目录 (原文件不动)。

把 classic 写法的 usersettings / 计划文件迁移为 dev 格式, 输出到一个**新目录**,
不修改原文件。框架运行期 (``UserConfig`` / ``CombatPlan`` 的 ``from_yaml``) 检测到
老版本字段会直接崩溃并提示运行本工具。

迁移内容 (见 :mod:`autowsgr.infra.config_compat`):

- ``ship_name_file`` / ``account.account`` / ``account.password`` → 删除
- ``delay`` → ``operation_delay_min`` / ``operation_delay_max``
- ``emulator_type`` / ``emulator_start_cmd`` / ``emulator_name`` → 嵌套 ``emulator`` 块
- ``check_update`` / ``show_map_node`` → 删除
- 计划文件 ``fleet`` 前导空占位 → 剥离 (1-indexed → 0-indexed)

用法
----
::

    # 迁移当前目录下的 usersettings.yaml 和 plans/ (默认输出 migrated_config/)
    python tools/migrate_config.py

    # 只迁移指定 usersettings
    python tools/migrate_config.py --usersettings path/to/usersettings.yaml

    # 只迁移指定计划目录
    python tools/migrate_config.py --planroot path/to/plans

    # 两者一起, 指定输出目录
    python tools/migrate_config.py --usersettings a.yaml --planroot plans --output out

可选参数
--------
    --usersettings PATH  用户配置 YAML (默认: 当前目录 usersettings.yaml)
    --planroot PATH      计划文件根目录 (默认: 当前目录 plans/)
    --output PATH        输出目录 (默认: migrated_config)
    --dry-run            只打印将迁移什么, 不写文件
    --force              输出目录已存在且非空时强制覆盖
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any


# ── 项目根路径 ───────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# ── UTF-8 输出兼容 (Windows 终端) ────────────────────────────────────────────
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # ty: ignore[call-non-callable]
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')  # ty: ignore[unresolved-attribute]
except Exception:  # noqa: S110
    pass

from autowsgr.infra.config_compat import (  # noqa: E402
    detect_legacy_plan,
    detect_legacy_user_config,
    migrate_plan_dict,
    migrate_raw_config,
)
from autowsgr.infra.file_utils import load_yaml, save_yaml  # noqa: E402


if TYPE_CHECKING:
    from collections.abc import Callable


_DEFAULT_USERSETTINGS = 'usersettings.yaml'
_DEFAULT_PLANROOT = 'plans'
_DEFAULT_OUTPUT = 'migrated_config'


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='把 classic 老版本配置迁移为 dev 格式, 输出到新目录 (原文件不动)。',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        '--usersettings',
        default=None,
        metavar='PATH',
        help=f'用户配置 YAML (默认: 当前目录 {_DEFAULT_USERSETTINGS})',
    )
    p.add_argument(
        '--planroot',
        default=None,
        metavar='PATH',
        help=f'计划文件根目录 (默认: 当前目录 {_DEFAULT_PLANROOT}/)',
    )
    p.add_argument(
        '--output',
        default=_DEFAULT_OUTPUT,
        metavar='PATH',
        help=f'输出目录 (默认: {_DEFAULT_OUTPUT})',
    )
    p.add_argument('--dry-run', action='store_true', help='只打印, 不写文件')
    p.add_argument(
        '--force',
        action='store_true',
        help='输出目录已存在且非空时强制覆盖',
    )
    return p.parse_args(argv)


def _resolve_inputs(
    args: argparse.Namespace,
) -> tuple[Path | None, Path | None]:
    """解析 usersettings / planroot 路径。

    显式指定时无条件采用 (后续在 main 里校验存在性); 未指定则取 cwd 默认,
    仅当默认路径真实存在时才纳入, 否则为 None (跳过)。
    """
    if args.usersettings:
        usersettings: Path | None = Path(args.usersettings)
    else:
        default_us = Path.cwd() / _DEFAULT_USERSETTINGS
        usersettings = default_us if default_us.exists() else None

    if args.planroot:
        planroot: Path | None = Path(args.planroot)
    else:
        default_pr = Path.cwd() / _DEFAULT_PLANROOT
        planroot = default_pr if default_pr.is_dir() else None

    return usersettings, planroot


def _prepare_output(output: Path, force: bool, dry_run: bool) -> bool:
    """检查 / 创建输出目录。返回是否可继续 (False = 报错中止)。"""
    if dry_run:
        return True
    if output.exists() and any(output.iterdir()):
        if not force:
            return False
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    return True


def _process(
    src: Path,
    dst: Path,
    detect: Callable[[Any], list[str]],
    migrate: Callable[[Any], Any],
    *,
    dry_run: bool,
) -> list[str]:
    """处理单个 YAML: 返回命中的老版本项; 非 dry-run 时写出。

    命中老版本 → ``migrate`` + :func:`save_yaml` (会丢注释, 仅影响需迁移的文件);
    干净 → 原样复制 (保留注释)。
    """
    data = load_yaml(src)
    legacy = detect(data)
    if dry_run:
        return legacy
    dst.parent.mkdir(parents=True, exist_ok=True)
    if legacy:
        migrate(data)
        save_yaml(data, dst)
    else:
        shutil.copy2(src, dst)
    return legacy


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912
    args = _parse_args(argv)
    usersettings, planroot = _resolve_inputs(args)

    print('=' * 60)
    print('  classic 配置迁移工具')
    print('=' * 60)
    print(f'  usersettings: {usersettings or "(未找到, 跳过)"}')
    print(f'  planroot:     {planroot or "(未找到, 跳过)"}')
    print(f'  输出目录:     {args.output}')
    print(f'  dry-run:      {args.dry_run}')
    print()

    if usersettings is None and planroot is None:
        print('  [ERROR] 未找到任何可迁移的配置 (usersettings.yaml / plans/)。')
        print('  请用 --usersettings / --planroot 显式指定路径。')
        return 1

    output = Path(args.output)
    if not _prepare_output(output, args.force, args.dry_run):
        print(
            f'  [ERROR] 输出目录 {output} 已存在且非空。'
            '请用 --output 指定其他路径, 或加 --force 覆盖。',
        )
        return 1

    total = 0
    migrated = 0

    # ── usersettings ──
    if usersettings is not None:
        if not usersettings.exists():
            print(f'  [WARN] usersettings 不存在: {usersettings}, 跳过。')
        else:
            dst = output / _DEFAULT_USERSETTINGS
            legacy = _process(
                usersettings,
                dst,
                detect_legacy_user_config,
                migrate_raw_config,
                dry_run=args.dry_run,
            )
            total += 1
            if legacy:
                migrated += 1
                print(f'  [迁移] {usersettings} → {dst}')
                for item in legacy:
                    print(f'          - {item}')
            else:
                print(f'  [跳过] {usersettings} (无需迁移, 原样复制)')

    # ── planroot ──
    if planroot is not None:
        plan_files = sorted(planroot.rglob('*.yaml'))
        if not plan_files:
            print(f'  [WARN] planroot 下无 .yaml 文件: {planroot}, 跳过。')
        else:
            print(f'  计划目录共 {len(plan_files)} 个 yaml 文件:')
            for src in plan_files:
                rel = src.relative_to(planroot)
                dst = output / _DEFAULT_PLANROOT / rel
                legacy = _process(
                    src,
                    dst,
                    detect_legacy_plan,
                    migrate_plan_dict,
                    dry_run=args.dry_run,
                )
                total += 1
                if legacy:
                    migrated += 1
                    print(f'  [迁移] {src} → {dst}')
                    for item in legacy:
                        print(f'          - {item}')
                # 干净的计划文件静默原样复制 (数量多, 不逐个打印)

    print()
    print(f'  处理 {total} 个文件, 其中 {migrated} 个做了迁移。')
    if args.dry_run:
        print('  [DRY-RUN] 未写入文件。')
    else:
        print(f'  新配置目录: {output.resolve()}')
        print('  请将运行指向该目录; 若 usersettings 引用了 plan_root, 请相应更新。')
    print('=' * 60)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
