"""模拟器层性能基准测试工具。

测试项目
--------
- **截图吞吐**：连续调用 ``controller.screenshot()`` 的平均耗时、帧率及分位数
- **点击延迟**：``controller.click()`` 的往返时间（RTT），含 adb 下行 + 设备响应
- **滑动延迟**：``controller.swipe()`` 的往返时间（RTT）
- **Shell RTT**：裸 ``adb shell echo`` 往返时间，作为基准下界
- **连接耗时**：``connect()`` 加载 & minicap 修复所需时间

用法
----
连接默认设备::

    python tools/benchmark_emulator.py

指定 serial::

    python tools/benchmark_emulator.py --serial 127.0.0.1:16384

调整批次::

    python tools/benchmark_emulator.py --shots 30 --clicks 50 --swipes 20

导出 JSON 报告::

    python tools/benchmark_emulator.py --json benchmark_result.json

只运行部分测试（跳过截图）::

    python tools/benchmark_emulator.py --skip screenshot
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Callable

# ── 将项目根目录加入 sys.path，兼容直接运行 ──
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from loguru import logger
from autowsgr.emulator.controller import ADBController


# ══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════════════════

def _percentile(data: list[float], p: float) -> float:
    """计算第 p 百分位（0–100）。"""
    if not data:
        return float("nan")
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (k - lo)


def _stats(samples: list[float]) -> dict:
    """从样本列表生成统计摘要（单位：毫秒）。"""
    ms = [x * 1000 for x in samples]
    n = len(ms)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "mean_ms": statistics.mean(ms),
        "min_ms": min(ms),
        "max_ms": max(ms),
        "std_ms": statistics.stdev(ms) if n > 1 else 0.0,
        "p50_ms": _percentile(ms, 50),
        "p90_ms": _percentile(ms, 90),
        "p99_ms": _percentile(ms, 99),
        "fps": 1000.0 / statistics.mean(ms) if statistics.mean(ms) > 0 else float("inf"),
    }


def _fmt_stats(label: str, s: dict) -> str:
    """格式化单项统计结果为可读字符串。"""
    if s.get("n", 0) == 0:
        return f"  {label}: 无数据"
    lines = [
        f"  {label} (n={s['n']})",
        f"    均值  : {s['mean_ms']:7.2f} ms",
        f"    最小  : {s['min_ms']:7.2f} ms",
        f"    最大  : {s['max_ms']:7.2f} ms",
        f"    标准差: {s['std_ms']:7.2f} ms",
        f"    p50   : {s['p50_ms']:7.2f} ms",
        f"    p90   : {s['p90_ms']:7.2f} ms",
        f"    p99   : {s['p99_ms']:7.2f} ms",
    ]
    if "fps" in s:
        lines.append(f"    吞吐率: {s['fps']:7.2f} fps")
    return "\n".join(lines)


def _progress_bar(done: int, total: int, width: int = 30) -> str:
    filled = int(width * done / total)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {done}/{total}"


# ══════════════════════════════════════════════════════════════════════════════
# 各测试项
# ══════════════════════════════════════════════════════════════════════════════

def bench_connect(ctrl: ADBController) -> dict:
    """测量 connect() 耗时（只做一次）。"""
    print("\n▶ 连接设备 …", end=" ", flush=True)
    t0 = time.monotonic()
    info = ctrl.connect()
    elapsed = time.monotonic() - t0
    print(f"完成  ({elapsed * 1000:.1f} ms)")
    print(f"  serial={info.serial}  分辨率={info.resolution[0]}x{info.resolution[1]}")
    return {"connect_ms": elapsed * 1000, "serial": info.serial, "resolution": list(info.resolution)}


def bench_screenshot(ctrl: ADBController, n: int = 20, warmup: int = 2) -> dict:
    """连续截图压力测试。

    Parameters
    ----------
    n:
        正式计时轮数。
    warmup:
        预热轮数（不计入统计）。
    """
    print(f"\n▶ 截图性能  (预热 {warmup} 次 + 正式 {n} 次)")
    # 预热
    for _ in range(warmup):
        ctrl.screenshot()

    samples: list[float] = []
    for i in range(n):
        t0 = time.monotonic()
        frame = ctrl.screenshot()
        elapsed = time.monotonic() - t0
        samples.append(elapsed)
        sys.stdout.write(f"\r  {_progress_bar(i + 1, n)}  {elapsed * 1000:6.1f} ms  frame={frame.shape[1]}x{frame.shape[0]}")
        sys.stdout.flush()
    print()

    s = _stats(samples)
    print(_fmt_stats("截图耗时", s))
    return {"screenshot": s}


def bench_click(ctrl: ADBController, n: int = 30, warmup: int = 3) -> dict:
    """点击延迟测试（全程点击屏幕中心）。

    注意：``click()`` 目前通过 ``adb shell input tap`` 实现，
    返回时间 = ADB 命令入队 + 设备执行 + adb 返回，**不含** UI 渲染响应。
    """
    cx, cy = 0.5, 0.5
    print(f"\n▶ 点击延迟  (中心点 {cx},{cy}，预热 {warmup} 次 + 正式 {n} 次)")
    for _ in range(warmup):
        ctrl.click(cx, cy)

    samples: list[float] = []
    for i in range(n):
        t0 = time.monotonic()
        ctrl.click(cx, cy)
        elapsed = time.monotonic() - t0
        samples.append(elapsed)
        sys.stdout.write(f"\r  {_progress_bar(i + 1, n)}  {elapsed * 1000:6.1f} ms")
        sys.stdout.flush()
    print()

    s = _stats(samples)
    print(_fmt_stats("点击 RTT", s))
    return {"click": s}


def bench_swipe(ctrl: ADBController, n: int = 10, warmup: int = 2) -> dict:
    """滑动延迟测试（左→右短滑，duration=0.3s）。"""
    x1, y1, x2, y2, dur = 0.3, 0.5, 0.7, 0.5, 0.3
    print(f"\n▶ 滑动延迟  (左→右，duration={dur}s，预热 {warmup} 次 + 正式 {n} 次)")
    for _ in range(warmup):
        ctrl.swipe(x1, y1, x2, y2, duration=dur)

    samples: list[float] = []
    for i in range(n):
        t0 = time.monotonic()
        ctrl.swipe(x1, y1, x2, y2, duration=dur)
        elapsed = time.monotonic() - t0
        samples.append(elapsed)
        sys.stdout.write(f"\r  {_progress_bar(i + 1, n)}  {elapsed * 1000:6.1f} ms")
        sys.stdout.flush()
    print()

    s = _stats(samples)
    print(_fmt_stats(f"滑动 RTT (含 {int(dur * 1000)}ms duration)", s))
    return {"swipe": s}


def bench_shell_rtt(ctrl: ADBController, n: int = 20, warmup: int = 3) -> dict:
    """裸 shell 往返时间（``adb shell echo ok``），作为通信基准下界。"""
    print(f"\n▶ Shell RTT  (adb shell echo ok，预热 {warmup} 次 + 正式 {n} 次)")
    for _ in range(warmup):
        ctrl.shell("echo ok")

    samples: list[float] = []
    for i in range(n):
        t0 = time.monotonic()
        ctrl.shell("echo ok")
        elapsed = time.monotonic() - t0
        samples.append(elapsed)
        sys.stdout.write(f"\r  {_progress_bar(i + 1, n)}  {elapsed * 1000:6.1f} ms")
        sys.stdout.flush()
    print()

    s = _stats(samples)
    print(_fmt_stats("Shell RTT", s))
    return {"shell_rtt": s}


def bench_screenshot_burst(ctrl: ADBController, duration: float = 5.0) -> dict:
    """在固定时间内尽可能多地连续截图，测量持续吞吐量。

    Parameters
    ----------
    duration:
        持续时间（秒）。
    """
    print(f"\n▶ 截图突发吞吐  (持续 {duration:.0f}s 连续截图)")
    deadline = time.monotonic() + duration
    samples: list[float] = []
    frame_count = 0

    while time.monotonic() < deadline:
        t0 = time.monotonic()
        ctrl.screenshot()
        samples.append(time.monotonic() - t0)
        frame_count += 1
        remaining = max(0.0, deadline - time.monotonic())
        sys.stdout.write(
            f"\r  已截 {frame_count} 帧  剩余 {remaining:.1f}s"
            f"  最近耗时 {samples[-1] * 1000:.1f} ms"
        )
        sys.stdout.flush()
    print()

    s = _stats(samples)
    print(_fmt_stats("突发截图耗时", s))
    return {"screenshot_burst": s}


# ══════════════════════════════════════════════════════════════════════════════
# 报告汇总
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(results: dict) -> None:
    """打印全局对比摘要表格。"""
    print("\n" + "═" * 62)
    print("  性能汇总")
    print("═" * 62)
    order = [
        ("connect_ms",       "连接耗时",         "ms",  None),
        ("screenshot",       "截图均值",          "ms",  "mean_ms"),
        ("screenshot",       "截图 p90",          "ms",  "p90_ms"),
        ("screenshot",       "截图吞吐",          "fps", "fps"),
        ("screenshot_burst", "突发截图均值",       "ms",  "mean_ms"),
        ("screenshot_burst", "突发吞吐",          "fps", "fps"),
        ("click",            "点击均值",          "ms",  "mean_ms"),
        ("click",            "点击 p90",          "ms",  "p90_ms"),
        ("swipe",            "滑动均值",          "ms",  "mean_ms"),
        ("shell_rtt",        "Shell RTT 均值",    "ms",  "mean_ms"),
        ("shell_rtt",        "Shell RTT p90",     "ms",  "p90_ms"),
    ]
    for key, label, unit, sub in order:
        if key == "connect_ms":
            val = results.get("connect_ms")
            if val is not None:
                print(f"  {label:<22} {val:>9.2f} {unit}")
        else:
            block = results.get(key)
            if block and isinstance(block, dict) and sub in block:
                val = block[sub]
                if not math.isnan(val):
                    print(f"  {label:<22} {val:>9.2f} {unit}")
    print("═" * 62)


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="模拟器层性能基准测试",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--serial", default=None, help="ADB serial（留空则自动检测）")
    p.add_argument("--shots",  type=int, default=20,  help="截图计时轮数")
    p.add_argument("--clicks", type=int, default=30,  help="点击计时轮数")
    p.add_argument("--swipes", type=int, default=10,  help="滑动计时轮数")
    p.add_argument("--shell",  type=int, default=20,  help="Shell RTT 计时轮数")
    p.add_argument("--burst",  type=float, default=5.0, help="突发截图持续秒数（0 跳过）")
    p.add_argument(
        "--skip",
        nargs="*",
        default=[],
        choices=["screenshot", "click", "swipe", "shell", "burst"],
        help="跳过指定测试项",
    )
    p.add_argument("--json", metavar="FILE", default=None, help="将结果输出到 JSON 文件")
    p.add_argument("--log-level", default="WARNING", help="日志级别（DEBUG / INFO / WARNING）")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # 配置 loguru
    logger.remove()
    logger.add(sys.stderr, level=args.log_level.upper(), colorize=True)

    print("╔══════════════════════════════════════════════════════════╗")
    print("║          AutoWSGR  Emulator  Benchmark                  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    if args.serial:
        print(f"  目标设备: {args.serial}")
    else:
        print("  目标设备: 自动检测")

    skip = set(args.skip or [])
    results: dict = {}

    ctrl = ADBController(serial=args.serial)

    # ── 连接 ──
    connect_result = bench_connect(ctrl)
    results.update(connect_result)

    try:
        # ── 截图 ──
        if "screenshot" not in skip:
            results.update(bench_screenshot(ctrl, n=args.shots))

        # ── 突发截图 ──
        if "burst" not in skip and args.burst > 0:
            results.update(bench_screenshot_burst(ctrl, duration=args.burst))

        # ── 点击 ──
        if "click" not in skip:
            results.update(bench_click(ctrl, n=args.clicks))

        # ── 滑动 ──
        if "swipe" not in skip:
            results.update(bench_swipe(ctrl, n=args.swipes))

        # ── Shell RTT ──
        if "shell" not in skip:
            results.update(bench_shell_rtt(ctrl, n=args.shell))

    finally:
        ctrl.disconnect()

    # ── 汇总 ──
    print_summary(results)

    # ── JSON 导出 ──
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n  结果已保存至: {out.resolve()}")


if __name__ == "__main__":
    main()
