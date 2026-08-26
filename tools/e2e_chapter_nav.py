"""E2E 实机测试: 侧边栏章节导航。

运行前请确保:
1. MuMu 模拟器已启动, adb 可连到 emulator-5554
2. 游戏官服已登录, 停在任意页面 (脚本自动确保就绪并进入地图页)
3. 本脚本在 AutoWSGR 项目根目录下用 .venv 运行

测试流程:
- 进入地图页, OCR 识别当前章 C0
- navigate_to_chapter(C0 - 3 if C0 > 3 else C0 + 3)  → 向中间方向跨 3 章 (每次单步±1, 实际跳 3 次)
- OCR 确认目标章到达
- navigate_to_chapter(1) → 跳回第 1 章
- navigate_to_chapter(10) → 跳到第 10 章
- navigate_to_chapter(1) → 再回到 1 章 (大跨度 9 章校验)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# 确保 autowsgr 包可导入
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from autowsgr.infra import (
    AccountConfig,
    EmulatorConfig,
    LogConfig,
    UserConfig,
)
from autowsgr.infra.config import OCRConfig
from autowsgr.types import GameAPP, PageName
from autowsgr.scheduler.launcher import Launcher
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.map.panels.sortie import SortiePanelMixin
from autowsgr.ui.map.base import BaseMapPage


def build_cfg() -> UserConfig:
    """构造最小运行配置。"""
    log_cfg = LogConfig(level='DEBUG')
    # 不持久化 DEBUG 到磁盘, 节省 IO
    return UserConfig(
        emulator=EmulatorConfig(serial='emulator-5554'),
        account=AccountConfig(game_app=GameAPP.official),
        ocr=OCRConfig(),
        log=log_cfg,
    )


def main() -> int:
    cfg = build_cfg()
    launcher = Launcher()
    launcher.set_config(cfg)
    # 手动触发日志初始化 (load_config 会做, 这里 set_config 后手动调)
    from autowsgr.infra.logger import setup_logger  # noqa: WPS433
    setup_logger(cfg.log.dir, cfg.log.level, save_images=True,
                 channels=cfg.log.effective_channels)

    logger.info('[E2E] 连接模拟器 emulator-5554 ...')
    launcher.connect()
    ctx = launcher.build_context()
    launcher.ensure_ready(ctx)  # 游戏停在主页面
    logger.info('[E2E] 游戏就绪')

    # ── 导航到地图页 ──
    logger.info('[E2E] 进入地图页')
    goto_page(ctx, PageName.MAP)

    # 构造面板控制器实例: 同时继承 SortiePanelMixin + BaseMapPage,
    # 这样 enter_sortie 用到的 ensure_panel / switch_panel 才不会 AttributeError。
    # SortiePanelMixin 本身也继承 BaseMapPage, 实际是同一祖先, MRO 不会冲突。
    class _Map(SortiePanelMixin, BaseMapPage):
        def __init__(self, ctx):
            # BaseMapPage.__init__ 会绑定 self._ctx / self._ctrl / self._ocr
            BaseMapPage.__init__(self, ctx)

    page = _Map(ctx)

    # ── 先 OCR 读一次当前章 ──
    info = None
    for _ in range(3):
        info = page.recognize_map(ctx.ctrl.screenshot(), ctx.ocr)
        if info is not None:
            break
        time.sleep(0.5)
    if info is None:
        logger.error('[E2E] 地图标题 OCR 失败, 无法继续')
        return 2
    cur_chapter = info.chapter
    logger.info('[E2E] 初始章: 第 {} 章 ({}-{} {})', cur_chapter, info.chapter, info.map_num, info.name)

    results: list[tuple[int, int, bool]] = []  # (from, to, ok)

    # ── Test 1: 向中间跨 3 章 (相对短路径) ──
    target1 = cur_chapter - 3 if cur_chapter > 5 else cur_chapter + 3
    if 1 <= target1 <= 10 and target1 != cur_chapter:
        logger.info('[E2E] === Test 1: 跳 {} → {} 章 ==='.format(cur_chapter, target1))
        result = page.navigate_to_chapter(target1)
        ok = result == target1
        logger.info('[E2E] Test 1 结果: 期望={} 实际={} {}'.format(target1, result, '✓' if ok else '✗'))
        results.append((cur_chapter, target1, ok))
        cur_chapter = result or target1
    else:
        logger.warning('[E2E] 跳过 Test 1 (边界章)')

    # ── Test 2: 跳回第 1 章 (若已在1章则跳过) ──
    if cur_chapter != 1:
        logger.info('[E2E] === Test 2: 跳 {} → 第 1 章 ==='.format(cur_chapter))
        result = page.navigate_to_chapter(1)
        ok = result == 1
        logger.info('[E2E] Test 2 结果: 期望=1 实际={} {}'.format(result, '✓' if ok else '✗'))
        results.append((cur_chapter, 1, ok))
        cur_chapter = result or 1
    else:
        logger.warning('[E2E] 跳过 Test 2 (已在第1章)')

    # ── Test 3: 跳 1 → 10 章 (大跨度 +9) ──
    if cur_chapter == 1:
        logger.info('[E2E] === Test 3: 跳 1 → 第 10 章 (大跨度 +9) ===')
        result = page.navigate_to_chapter(10)
        ok = result == 10
        logger.info('[E2E] Test 3 结果: 期望=10 实际={} {}'.format(result, '✓' if ok else '✗'))
        results.append((1, 10, ok))
        cur_chapter = result or 10

    # ── Test 4: 跳 10 → 1 章 (大跨度 -9) ──
    if cur_chapter == 10:
        logger.info('[E2E] === Test 4: 跳 10 → 第 1 章 (大跨度 -9) ===')
        result = page.navigate_to_chapter(1)
        ok = result == 1
        logger.info('[E2E] Test 4 结果: 期望=1 实际={} {}'.format(result, '✓' if ok else '✗'))
        results.append((10, 1, ok))
        cur_chapter = result or 1

    # ── Test 5: 1 → 2 → 3 单步校验 ──
    if cur_chapter == 1:
        logger.info('[E2E] === Test 5: 1→2→3 连续单步 ===')
        r2 = page.navigate_to_chapter(2)
        r3 = page.navigate_to_chapter(3) if r2 == 2 else None
        ok = r2 == 2 and r3 == 3
        logger.info('[E2E] Test 5 结果: 期望=2,3 实际={},{} {}'.format(r2, r3, '✓' if ok else '✗'))
        results.append((1, 3, ok))

    # ── Test 6: 真实进入 2-1 出征准备页（全链路 章→关卡→准备页） ──
    logger.info('[E2E] === Test 6: enter_sortie(2, 1) 真实点击进入出征准备页 ===')
    ok6 = False
    try:
        # 先确保停在 第 2 章 (若从 Test 5 的 3 出发则回退一步)
        page.navigate_to_chapter(2)
        # 进入出征准备页 (内部会 navigate_to_map(1) + CLICK_ENTER_SORTIE)
        page.enter_sortie(2, 1)
        # 不抛 NavigationError 就是成功。立即返回地图页, 避免留在准备页污染后续。
        logger.info('[E2E] Test 6: enter_sortie 无异常, 尝试返回地图页')
        ctx.ctrl.press_back()
        time.sleep(1.2)
        from autowsgr.ui.utils import wait_for_page  # noqa: WPS433
        wait_for_page(ctx.ctrl, BaseMapPage.is_current_page, timeout=8.0,
                      source='出征准备返回', target=PageName.MAP)
        # 回到地图页后再次 OCR, 确认当前就是 2-1 (说明真的停在目标图而不是乱跳)
        info6 = None
        for _ in range(3):
            info6 = page.recognize_map(ctx.ctrl.screenshot(), ctx.ocr)
            if info6 is not None:
                break
            time.sleep(0.3)
        if info6 is not None and info6.chapter == 2 and info6.map_num == 1:
            ok6 = True
            logger.info('[E2E] Test 6 结果: 2-1→出征准备页 ✓，返回后 OCR={}-{} {} ✓'.format(
                info6.chapter, info6.map_num, info6.name))
        else:
            logger.warning('[E2E] Test 6 返回后章/节校验异常: {}'.format(info6))
    except Exception as e:  # noqa: BLE001
        logger.exception('[E2E] Test 6 失败: {}'.format(e))
        # 失败时强制兜底返回, 不污染后续流程或其他脚本
        try:
            ctx.ctrl.press_back()
            time.sleep(1.0)
        except Exception:
            pass
    results.append((2, 1, ok6))

    # ── 汇总 ──
    total = len(results)
    passed = sum(1 for _, _, ok in results if ok)
    failed = total - passed
    logger.info('=' * 60)
    logger.info('[E2E] 汇总: 共 {} 项, 通过 {}, 失败 {}'.format(total, passed, failed))
    for i, (frm, to, ok) in enumerate(results, 1):
        logger.info('  Test {}: {}→{}  {}'.format(i, frm, to, '✓' if ok else '✗'))
    logger.info('=' * 60)
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
