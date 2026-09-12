"""E2E 快速实机验证入口 — case 发现、参数路由、执行与退出码。

用法::

    # 列出全部可用 case
    python tools/e2e/run.py --list

    # 链路自检 (只连接 + 截图, 不动游戏状态)
    python tools/e2e/run.py screenshot --no-launch

    # 跑一次常规战 (编队识别需要 OCR)
    python tools/e2e/run.py normal_fight --with-ocr --plan 1-1 --times 1

    # 指定设备与调试日志
    python tools/e2e/run.py --serial 127.0.0.1:16384 --debug screenshot

参数顺序约定: 全局参数可放在 case 名之前或之后, case 参数跟随 case。
全局参数: --serial SERIAL / --debug / --no-launch / --with-ocr / --fast-ocr / --list。
其余参数由 case 自己的 add_arguments(parser) 定义并解析 (见 cases/ 示例)。
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any


# 处理 Windows GBK 编码兼容性
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: S110
    pass

# 保证仓库根可导入 (直接 python tools/e2e/run.py 运行时 sys.path[0] 是 tools/e2e)
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_CASES_DIR = Path(__file__).parent / 'cases'


# ═══════════════════════════════════════════════════════════════════════════════
# case 发现与加载
# ═══════════════════════════════════════════════════════════════════════════════


def load_cases() -> dict[str, Any]:
    """扫描 cases/ 目录, 加载所有带 run() 的验证脚本。

    case 约定 (见 cases/ 内示例):
    - 必须定义 ``run(rt) -> bool``: 步骤主体, 返回整体判定;
    - 可选 ``DESC: str``: 一句话描述, --list 时显示;
    - 可选 ``add_arguments(parser)``: 定义 case 专属命令行参数。
    """
    cases: dict[str, Any] = {}
    if not _CASES_DIR.exists():
        return cases
    for py in sorted(_CASES_DIR.glob('*.py')):
        if py.name.startswith('_'):
            continue
        spec = importlib.util.spec_from_file_location(f'tools.e2e.cases.{py.stem}', py)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, 'run'):
            cases[py.stem] = mod
    return cases


def print_case_list(cases: dict[str, Any]) -> None:
    """打印全部 case 及其描述。"""
    print()
    print('═' * 68)
    print('  可用 E2E 验证 case')
    print('═' * 68)
    if not cases:
        print(f'  (cases 目录为空: {_CASES_DIR})')
    for name, mod in cases.items():
        desc = getattr(mod, 'DESC', '')
        print(f'  {name:24s} {desc}')
    print()
    print('  运行: python tools/e2e/run.py <case> [全局参数在前, case 参数在后]')
    print('  全局: --serial SERIAL / --debug / --no-launch / --preserve-state / --with-ocr')
    print('═' * 68)


# ═══════════════════════════════════════════════════════════════════════════════
# 参数切分: [全局参数] <case名> [case参数]
# ═══════════════════════════════════════════════════════════════════════════════


def split_argv(argv: list[str]) -> tuple[list[str], str | None, list[str]]:
    """把 argv 切成 (全局参数, case 名, case 参数)。

    全局参数可出现在 case 名之前或之后; ``--serial`` 带一个值;
    第一个非 ``-`` 开头的 token 视为 case 名, 其余非全局 token 归 case 参数。
    """
    global_flags = {
        '--debug',
        '--fast-ocr',
        '--list',
        '--no-launch',
        '--preserve-state',
        '--with-ocr',
    }
    global_args: list[str] = []
    case_name: str | None = None
    case_args: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == '--serial' and i + 1 < len(argv):
            global_args.extend(argv[i : i + 2])
            i += 2  # --serial 及其值
            continue
        if tok in global_flags:
            global_args.append(tok)
            i += 1
            continue
        if case_name is None and not tok.startswith('-'):
            case_name = tok
        elif case_name is None:
            global_args.append(tok)
        else:
            case_args.append(tok)
        i += 1
    return global_args, case_name, case_args


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> int:
    global_argv, case_name, rest = split_argv(sys.argv[1:])

    cases = load_cases()

    # --list 或未指定 case: 打印列表后退出
    if '--list' in global_argv or case_name is None:
        print_case_list(cases)
        return 0

    mod = cases.get(case_name)
    if mod is None:
        print(f'未知 case: {case_name}')
        print_case_list(cases)
        return 2

    # 全局参数
    gp = argparse.ArgumentParser(add_help=False)
    gp.add_argument('--serial', default=None, help='ADB 设备序列号 (默认用配置)')
    gp.add_argument('--debug', action='store_true', help='DEBUG 日志')
    gp.add_argument('--no-launch', action='store_true', help='跳过游戏就绪 (只读验证)')
    gp.add_argument(
        '--preserve-state',
        action='store_true',
        help='连接后保留设备当前页面，不自动回到首页',
    )
    gp.add_argument('--with-ocr', action='store_true', help='初始化 OCR 引擎')
    gp.add_argument('--fast-ocr', action='store_true', help='本次运行使用 CPU FastOCR')
    g = gp.parse_args(global_argv)

    # case 参数 (由 case 自己定义; 未定义 add_arguments 时 rest 必须为空)
    cp = argparse.ArgumentParser(
        prog=f'e2e {case_name}',
        description=getattr(mod, 'DESC', ''),
    )
    if hasattr(mod, 'add_arguments'):
        mod.add_arguments(cp)
    case_args = cp.parse_args(rest)

    print()
    print('═' * 68)
    print(f'  E2E: {case_name} — {getattr(mod, "DESC", "")}')
    print('═' * 68)
    print(f'  设备: {g.serial or "自动检测 (usersettings.yaml)"}')
    print(
        f'  模式: {"只读 (跳过游戏就绪)" if g.no_launch else "完整 (游戏就绪)"}'
        f'{" + 保留当前状态" if g.preserve_state else ""}'
        f'{" + OCR" if g.with_ocr else ""}{" + FastOCR" if g.fast_ocr else ""}'
    )

    # 执行
    from tools.e2e.framework import E2ERunner

    rt = E2ERunner(
        case_name,
        case_args,
        serial=g.serial,
        debug=g.debug,
        no_launch=g.no_launch,
        preserve_state=g.preserve_state,
        with_ocr=g.with_ocr,
        fast_ocr=g.fast_ocr,
    )
    if not rt.prepare():
        return rt.finalize(overall=False)
    overall = False
    try:
        overall = bool(mod.run(rt))
    except SystemExit:
        # finalize() 位于 finally，保证显式退出也执行回主页/断开连接。
        raise
    except Exception as exc:
        rt.unexpected(exc)
    finally:
        rt.finalize(overall=overall)
    return 0 if overall and rt.state.failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
