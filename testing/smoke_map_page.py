"""地图页面交互式测试 — 人类监督下验证 UI 控制器。

运行方式::

    # 使用默认 serial
    python testing/smoke_map_page.py

    # 指定 serial
    python testing/smoke_map_page.py emulator-5554

    # DEBUG 模式
    python testing/smoke_map_page.py emulator-5554 --debug

前置条件：
    1. 模拟器已启动
    2. 游戏已打开并进入 **地图选择** 页面 (出征 tab)
       （从主页 → 出征）

测试流程：
    1. 连接设备 → 截图 → 验证当前是否为地图页面
    2. 读取当前状态（面板、远征通知、章节位置）
    3. 尝试 OCR 识别地图标题
    4. 切换面板 (出征 → 演习 → 出征)
    5. 切换章节 (上一章 / 下一章)
    6. 回退
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ── 把项目根目录加入 path ──
sys.path.insert(0, str(Path(__file__).parent.parent))

from autowsgr.emulator.controller import ADBController
from autowsgr.infra.logger import save_image, setup_logger
from autowsgr.ui.map_page import MAP_DATABASE, MapPage, MapPanel
from autowsgr.vision.matcher import PixelChecker
from autowsgr.vision.ocr import OCREngine

# ── 配置 ──

LOG_DIR = Path("logs/smoke")
PAUSE_AFTER_ACTION = 1.0  # 每个动作执行后等待秒数


# ── 工具函数 ──


def step(title: str) -> str:
    """打印步骤标题，询问是否执行。

    Returns
    -------
    str
        ``"run"`` / ``"skip"`` / ``"quit"``
    """
    print()
    print("─" * 60)
    print(f"  步骤: {title}")
    print("─" * 60)
    ans = input("  [Enter] 执行  |  [s] 跳过  |  [q] 退出: ").strip().lower()
    if ans == "q":
        print("  用户中止测试。")
        sys.exit(0)
    return "skip" if ans == "s" else "run"


def retry_prompt() -> bool:
    """步骤完成后询问是否重试。

    Returns
    -------
    bool
        ``True`` 表示重试当前步骤，``False`` 表示继续。
    """
    ans = input("  [Enter] 继续下一步  |  [r] 重试此步骤: ").strip().lower()
    return ans == "r"


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def info(msg: str) -> None:
    print(f"  ℹ {msg}")


def read_state(ctrl: ADBController, tag: str = "") -> None:
    """截图并报告页面状态。"""
    screen = ctrl.screenshot()
    if tag:
        save_image(screen, tag=f"map_{tag}")

    is_page = MapPage.is_current_page(screen)
    panel = MapPage.get_active_panel(screen)
    has_exp = MapPage.has_expedition_notification(screen)
    chapter_y = MapPage.find_selected_chapter_y(screen)

    info(f"is_current_page: {is_page}")
    info(f"active_panel: {panel}")
    info(f"has_expedition_notification: {has_exp}")
    info(f"selected_chapter_y: {chapter_y:.3f}" if chapter_y else "selected_chapter_y: None")


def verify_panel(ctrl: ADBController, expected: MapPanel) -> None:
    """验证当前面板状态。"""
    screen = ctrl.screenshot()
    actual = MapPage.get_active_panel(screen)
    if actual == expected:
        ok(f"面板正确: {expected.value}")
    else:
        fail(f"面板不符: 期望 {expected.value}, 实际 {actual}")


# ── 主测试流程 ──


def main() -> None:
    # ── 解析参数 ──
    serial = None
    debug = False
    for arg in sys.argv[1:]:
        if arg == "--debug":
            debug = True
        else:
            serial = arg

    setup_logger(
        log_dir=LOG_DIR,
        level="DEBUG" if debug else "INFO",
        save_images=True,
    )

    print()
    print("═" * 60)
    print("  地图页面交互式测试")
    print("═" * 60)
    print()
    print("  请确保游戏已打开并进入【地图选择】页面 (出征 tab)")
    print("  每个步骤完成后可按 [r] 重试 (人工切换页面后再跑)")
    print()

    # ── Step 1: 连接设备 ──
    if step("连接设备并截图") == "run":
        ctrl = ADBController(serial=serial, screenshot_timeout=15.0)
        ctrl.connect()
        ok(f"已连接: {ctrl._serial}")

        screen = ctrl.screenshot()
        save_image(screen, tag="map_step1_connect")

        if MapPage.is_current_page(screen):
            ok("当前页面为地图选择页面")
        else:
            fail("当前页面不是地图选择页面！")
            info("请确认游戏画面，然后决定是否继续")
    else:
        print("  跳过连接，退出")
        return

    # ── Step 2: 读取初始状态 ──
    while step("读取当前状态") == "run":
        read_state(ctrl, tag="step2_initial")
        if not retry_prompt():
            break

    # ── Step 3: OCR 地图标题 ──
    ocr = None
    while step("OCR 识别地图标题") == "run":
        if ocr is None:
            info("正在初始化 OCR 引擎 (EasyOCR)...")
            try:
                ocr = OCREngine.create("easyocr", gpu=False)
                ok("OCR 引擎初始化成功")
            except ImportError:
                fail("EasyOCR 未安装，跳过 OCR 测试")
                info("安装: pip install easyocr")
                break
            except Exception as e:
                fail(f"OCR 引擎初始化异常: {e}")
                break

        try:
            screen = ctrl.screenshot()
            from autowsgr.ui.map_page import TITLE_CROP_REGION

            x1, y1, x2, y2 = TITLE_CROP_REGION
            cropped = PixelChecker.crop(screen, x1, y1, x2, y2)
            save_image(cropped, tag="map_step3_title_crop")

            map_info = MapPage.recognize_map(screen, ocr)
            if map_info:
                ok(f"地图识别: 第{map_info.chapter}章 {map_info.chapter}-{map_info.map_num} {map_info.name}")
                info(f"  原始文本: '{map_info.raw_text}'")
                # 校验是否在数据库中
                db_name = MAP_DATABASE.get((map_info.chapter, map_info.map_num))
                if db_name:
                    if db_name == map_info.name:
                        ok(f"  数据库匹配: ✓")
                    else:
                        info(f"  数据库名称: '{db_name}' (OCR: '{map_info.name}')")
                else:
                    info(f"  ({map_info.chapter}, {map_info.map_num}) 不在数据库中")
            else:
                fail("OCR 未能识别地图标题")
                info("请检查裁切区域和 OCR 结果")

                # 尝试输出原始 OCR 结果
                results = ocr.recognize(cropped)
                for r in results:
                    info(f"  OCR 结果: text='{r.text}' conf={r.confidence:.2f}")
        except Exception as e:
            fail(f"OCR 测试异常: {e}")

        if not retry_prompt():
            break

    # ── Step 4: 切换面板到演习 ──
    while step("切换到演习面板") == "run":
        page = MapPage(ctrl)
        page.switch_panel(MapPanel.EXERCISE)
        time.sleep(PAUSE_AFTER_ACTION)
        verify_panel(ctrl, MapPanel.EXERCISE)
        save_image(ctrl.screenshot(), tag="map_step4_exercise")
        if not retry_prompt():
            break

    # ── Step 5: 切换面板到远征 ──
    while step("切换到远征面板") == "run":
        page = MapPage(ctrl)
        page.switch_panel(MapPanel.EXPEDITION)
        time.sleep(PAUSE_AFTER_ACTION)
        verify_panel(ctrl, MapPanel.EXPEDITION)
        save_image(ctrl.screenshot(), tag="map_step5_expedition")
        if not retry_prompt():
            break

    # ── Step 6: 切回出征面板 ──
    while step("切回出征面板") == "run":
        page = MapPage(ctrl)
        page.switch_panel(MapPanel.SORTIE)
        time.sleep(PAUSE_AFTER_ACTION)
        verify_panel(ctrl, MapPanel.SORTIE)
        save_image(ctrl.screenshot(), tag="map_step6_sortie")
        if not retry_prompt():
            break

    # ── Step 7: 切换到上一章 ──
    while step("切换到上一章") == "run":
        page = MapPage(ctrl)
        screen = ctrl.screenshot()
        chapter_y_before = MapPage.find_selected_chapter_y(screen)
        info(f"切换前章节 y: {chapter_y_before:.3f}" if chapter_y_before else "切换前: 未找到选中章节")

        result = page.click_prev_chapter(screen)
        if result:
            ok("已点击上一章")
            time.sleep(PAUSE_AFTER_ACTION)

            screen2 = ctrl.screenshot()
            save_image(screen2, tag="map_step7_prev_chapter")
            chapter_y_after = MapPage.find_selected_chapter_y(screen2)
            info(f"切换后章节 y: {chapter_y_after:.3f}" if chapter_y_after else "切换后: 未找到选中章节")

            # 尝试 OCR 验证
            if ocr:
                map_info = MapPage.recognize_map(screen2, ocr)
                if map_info:
                    ok(f"当前地图: {map_info.chapter}-{map_info.map_num} {map_info.name}")
        else:
            fail("无法点击上一章 (可能已在最前)")

        if not retry_prompt():
            break

    # ── Step 8: 切换到下一章 (回到原来) ──
    while step("切换到下一章 (回到原来的章节)") == "run":
        page = MapPage(ctrl)
        screen = ctrl.screenshot()

        result = page.click_next_chapter(screen)
        if result:
            ok("已点击下一章")
            time.sleep(PAUSE_AFTER_ACTION)

            screen2 = ctrl.screenshot()
            save_image(screen2, tag="map_step8_next_chapter")

            if ocr:
                map_info = MapPage.recognize_map(screen2, ocr)
                if map_info:
                    ok(f"当前地图: {map_info.chapter}-{map_info.map_num} {map_info.name}")
        else:
            fail("无法点击下一章 (可能已在最后)")

        if not retry_prompt():
            break

    # ── Step 9: 最终状态 ──
    while step("读取最终状态") == "run":
        read_state(ctrl, tag="step9_final")
        if not retry_prompt():
            break

    # ── Step 10: 回退 ──
    if step("点击回退按钮") == "run":
        page = MapPage(ctrl)
        page.go_back()
        time.sleep(PAUSE_AFTER_ACTION)
        screen = ctrl.screenshot()
        save_image(screen, tag="map_step10_back")

        if MapPage.is_current_page(screen):
            info("仍在地图页面 (可能回退到上级菜单需要更多步骤)")
        else:
            ok("已离开地图页面")

    # ── 断开连接 ──
    ctrl.disconnect()
    print()
    print("═" * 60)
    print("  测试结束")
    print("═" * 60)


if __name__ == "__main__":
    main()
