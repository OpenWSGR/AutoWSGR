#!/usr/bin/env python
"""一键运行所有 UI 控制器 e2e 测试。

用法::

    python testing/ui/run_all_e2e.py [--serial SERIAL] [--debug] [--pause SECONDS] [--parallel N] [--no-cleanup]

选项:
    --serial SERIAL       ADB 设备序列号（默认自动检测）
    --debug              启用调试日志
    --pause SECONDS      每步操作等待时间（默认 1.5）
    --parallel N         并行运行 N 个测试（默认 1，即序列运行）
    --no-cleanup         不清理日志目录中的旧文件

流程:
    1. 自动搜索 `testing/ui/*/e2e.py` 所有测试脚本
    2. 按顺序或并行执行，均为 --auto 自动模式
    3. 收集每个测试的退出码和输出日志
    4. 汇总统计，输出综合报告
    5. 返回汇总结果 (0 = 全过 / 1 = 有失败)
"""

from __future__ import annotations

import argparse
import io
import json
import runpy
import shutil
import sys
from dataclasses import dataclass, field

# 处理 Windows GBK 编码兼容性
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass  # 如果 reconfigure 不可用，继续使用默认编码
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TestResult:
    """单个 e2e 测试的运行结果。"""
    name: str                  # 测试名称 (如 'main_page')
    script_path: Path          # e2e.py 脚本路径
    exit_code: int             # 退出码
    stdout: str = ""           # 标准输出
    stderr: str = ""           # 标准错误
    start_time: str = ""       # 启动时间 ISO
    end_time: str = ""         # 完成时间 ISO
    log_dir: Path | None = None
    report_file: Path | None = None
    
    @property
    def passed(self) -> bool:
        return self.exit_code == 0
    
    @property
    def duration_sec(self) -> float:
        if self.start_time and self.end_time:
            try:
                start = datetime.fromisoformat(self.start_time)
                end = datetime.fromisoformat(self.end_time)
                return (end - start).total_seconds()
            except Exception:
                return 0.0
        return 0.0


@dataclass
class TestRunReport:
    """所有测试的汇总报告。"""
    start_time: str
    end_time: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    results: list[TestResult] = field(default_factory=list)
    
    def add_result(self, result: TestResult) -> None:
        self.results.append(result)
        self.total_tests += 1
        if result.passed:
            self.passed += 1
        else:
            self.failed += 1
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "results": [
                {
                    "name": r.name,
                    "exit_code": r.exit_code,
                    "passed": r.passed,
                    "duration_sec": r.duration_sec,
                    "log_dir": str(r.log_dir) if r.log_dir else None,
                    "report_file": str(r.report_file) if r.report_file else None,
                    "stdout_log": str(Path("logs/e2e_all") / r.name / "stdout.log"),
                    "stderr_log": str(Path("logs/e2e_all") / r.name / "stderr.log"),
                }
                for r in self.results
            ],
        }


class _TeeWriter:
    """同时写入原始流和内存缓冲，用于捕获输出的同时保留实时显示。"""

    def __init__(self, primary: "Any", secondary: io.StringIO) -> None:
        self._primary = primary
        self._secondary = secondary

    def write(self, data: str) -> int:
        self._primary.write(data)
        self._secondary.write(data)
        return len(data)

    def flush(self) -> None:
        self._primary.flush()
        self._secondary.flush()

    def __getattr__(self, name: str) -> "Any":
        return getattr(self._primary, name)


def find_e2e_scripts(root_dir: Path) -> list[tuple[str, Path]]:
    """找到所有 e2e.py 脚本。
    
    Returns:
        [(controller_name, script_path), ...]
    """
    scripts = []
    for script_path in sorted(root_dir.glob("*/e2e.py")):
        name = script_path.parent.name
        scripts.append((name, script_path))
    return scripts


def run_e2e_test(
    script_path: Path,
    name: str,
    serial: str | None = None,
    debug: bool = False,
    pause: float = 1.5,
) -> TestResult:
    """运行单个 e2e 脚本。
    
    Parameters
    ----------
    script_path:
        e2e.py 脚本路径
    name:
        控制器名称 (用于日志)
    serial:
        ADB 设备序列号
    debug:
        启用调试日志
    pause:
        每步等待时间
    
    Returns
    -------
    TestResult
        测试结果对象
    """
    result = TestResult(
        name=name,
        script_path=script_path,
        exit_code=-1,
        start_time=datetime.now().isoformat(),
    )

    # 为每个测试准备日志目录
    test_log_dir = Path("logs/e2e_all") / name
    test_log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = test_log_dir / "stdout.log"
    stderr_log = test_log_dir / "stderr.log"

    # 构造传给脚本的 argv
    fake_argv = [str(script_path), "--auto"]
    if serial:
        fake_argv.append(serial)
    if debug:
        fake_argv.append("--debug")
    if pause != 1.5:
        fake_argv.extend(["--pause", str(pause)])

    # 捕获输出 + 保留 tee 到真实 stdout，方便实时观察
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    orig_argv = sys.argv
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr

    try:
        sys.argv = fake_argv
        sys.stdout = _TeeWriter(orig_stdout, stdout_buf)
        sys.stderr = _TeeWriter(orig_stderr, stderr_buf)

        runpy.run_path(str(script_path), run_name="__main__")
        result.exit_code = 0

    except SystemExit as exc:
        result.exit_code = int(exc.code) if exc.code is not None else 0
    except Exception as exc:
        import traceback
        result.exit_code = 1
        print(traceback.format_exc(), file=sys.stderr)
    finally:
        sys.argv = orig_argv
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        result.end_time = datetime.now().isoformat()

    result.stdout = stdout_buf.getvalue()
    result.stderr = stderr_buf.getvalue()
    stdout_log.write_text(result.stdout, encoding="utf-8")
    stderr_log.write_text(result.stderr, encoding="utf-8")

    # 尝试找到生成的报告文件
    report_search = Path("logs/e2e") / name
    report_file = report_search / f"e2e_report_{name}.json"
    if report_file.exists():
        result.log_dir = report_search
        result.report_file = report_file

    return result


def run_all_tests(
    root_dir: Path,
    serial: str | None = None,
    debug: bool = False,
    pause: float = 1.5,
    parallel: int = 1,
) -> TestRunReport:
    """运行所有 e2e 测试。
    
    Parameters
    ----------
    root_dir:
        UI 测试根目录 (testing/ui)
    serial:
        ADB 设备序列号
    debug:
        启用调试日志
    pause:
        每步等待时间
    parallel:
        并行数量（当前实现为序列运行）
    
    Returns
    -------
    TestRunReport
        汇总报告
    """
    scripts = find_e2e_scripts(root_dir)
    if not scripts:
        print("  未找到任何 e2e.py 脚本！")
        sys.exit(1)
    
    report = TestRunReport(
        start_time=datetime.now().isoformat(),
        end_time="",
    )
    
    _print_header(f"自动化 e2e 测试运行 (找到 {len(scripts)} 个测试)")
    print()
    print(f"  设备    : {serial or '自动检测'}")
    print(f"  调试    : {'启用' if debug else '禁用'}")
    print(f"  等待    : {pause:.1f}s")
    print(f"  并行    : {parallel}")
    print()
    
    for idx, (name, script_path) in enumerate(scripts, 1):
        print(f"[{idx}/{len(scripts)}] 运行 {name:25s}", end=" ", flush=True)
        result = run_e2e_test(script_path, name, serial, debug, pause)
        report.add_result(result)
        
        symbol = "[+]" if result.passed else "[-]"
        status = "PASS" if result.passed else f"FAIL(exit {result.exit_code})"
        duration = f"{result.duration_sec:.1f}s" if result.duration_sec > 0 else "?"
        print(f"{symbol} {status:20s} ({duration})")
    
    report.end_time = datetime.now().isoformat()
    return report


def print_summary(report: TestRunReport) -> None:
    """打印测试汇总。"""
    _print_header("e2e 测试汇总")
    print()
    
    for result in report.results:
        symbol = "[+]" if result.passed else "[-]"
        status = f"{result.exit_code:3d}"
        duration = f"{result.duration_sec:6.1f}s" if result.duration_sec > 0 else "      ?s"
        print(
            f"  {symbol} {result.name:25s} "
            f"exit={status} {duration}"
        )
    
    print()
    total_duration = 0.0
    for result in report.results:
        total_duration += result.duration_sec
    
    print(f"  总计: {report.total_tests} 个测试")
    print(f"  通过: {report.passed} 个 ({report.passed*100//report.total_tests if report.total_tests else 0}%)")
    print(f"  失败: {report.failed} 个")
    print(f"  耗时: {total_duration:.1f}s")
    print()
    
    if report.failed == 0:
        print("  [OK] 全部测试通过！")
    else:
        print(f"  [FAIL] {report.failed} 个测试失败")
        print()
        print("  失败测试列表:")
        for result in report.results:
            if not result.passed:
                log_hint = f"logs/e2e_all/{result.name}/"
                print(f"    - {result.name} (exit {result.exit_code})  -> {log_hint}")
    
    print("=" * 68)
    print(f"  详细日志目录: logs/e2e_all/")


def save_report(report: TestRunReport, output_path: Path) -> None:
    """保存 JSON 报告。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = report.to_dict()
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  报告已保存: {output_path.resolve()}")


def _print_header(title: str) -> None:
    print()
    print("═" * 68)
    print(f"  {title}")
    print("═" * 68)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="一键运行所有 UI 控制器 e2e 测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--serial",
        type=str,
        default=None,
        help="ADB 设备序列号（默认自动检测）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试日志",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=1.5,
        help="每步操作等待时间（秒，默认 1.5）",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="并行运行数量（默认 1，即序列运行）",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="不清理日志目录中的旧文件",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="logs/e2e_summary.json",
        help="汇总报告输出路径（默认 logs/e2e_summary.json）",
    )
    
    args = parser.parse_args()
    
    # 确定 testing/ui 目录
    root_dir = Path(__file__).parent
    if not root_dir.name == "ui" or not (root_dir / "_framework.py").exists():
        print(f"错误: 请从 testing/ui 目录运行此脚本或直接运行该目录下的脚本")
        sys.exit(1)
    
    # 运行所有测试
    report = run_all_tests(
        root_dir,
        serial=args.serial,
        debug=args.debug,
        pause=args.pause,
        parallel=args.parallel,
    )
    
    # 输出汇总
    print()
    print_summary(report)
    
    # 保存报告
    output_path = Path(args.output)
    save_report(report, output_path)
    
    # 返回正确的退出码
    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
