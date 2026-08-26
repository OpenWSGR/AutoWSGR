"""重构契约回归检查: 确认 sortie.py 对外 API 与拆分方案一致。

运行: .venv\\Scripts\\python.exe tools\\check_sortie_api.py
返回 0=通过, 非0=失败。
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    errors: list[str] = []

    # ── 1. counters 子模块必须存在（拆分后） ──
    try:
        from autowsgr.ui.map.panels import sortie_counters  # noqa: F401
        print('[OK]   sortie_counters.py 可导入')
    except Exception as e:  # noqa: BLE001
        errors.append(f'sortie_counters 不可导入: {e}')

    # ── 2. sortie.py 对外契约（3 调用方依赖）必须完全可导入 ──
    # panels/__init__.py 依赖
    try:
        from autowsgr.ui.map.panels.sortie import (
            LootShipCount,
            SortiePanelMixin,
            recognize_loot_count,
            recognize_ship_count,
        )
        print('[OK]   panels/__init__ 需要的 4 符号可导入')
    except Exception as e:  # noqa: BLE001
        errors.append(f'panels/__init__ 导入失败: {e}')

    # campaign.py 依赖
    try:
        from autowsgr.ui.map.panels.sortie import (
            LOOT_MAX,
            SHIP_MAX,
            recognize_loot_count,
            recognize_ship_count,
        )
        if LOOT_MAX != 50:
            errors.append(f'LOOT_MAX={LOOT_MAX}, 期望 50')
        if SHIP_MAX != 500:
            errors.append(f'SHIP_MAX={SHIP_MAX}, 期望 500')
        print('[OK]   campaign 需要的 4 符号可导入 + 常量值正确')
    except Exception as e:  # noqa: BLE001
        errors.append(f'campaign 导入失败: {e}')

    # e2e_chapter_nav.py 依赖
    try:
        from autowsgr.ui.map.panels.sortie import SortiePanelMixin  # noqa: F811
        print('[OK]   e2e 需要的 SortiePanelMixin 可导入')
    except Exception as e:  # noqa: BLE001
        errors.append(f'e2e 导入失败: {e}')

    # ── 3. 类注解 / 函数签名验证 ──
    # LootShipCount: frozen dataclass 字段 loot/loot_max/ship/ship_max
    try:
        fields = LootShipCount.__dataclass_fields__  # type: ignore[attr-defined]
        expected = ('loot', 'loot_max', 'ship', 'ship_max')
        missing = [f for f in expected if f not in fields]
        if missing:
            errors.append(f'LootShipCount 缺字段: {missing}')
        else:
            print('[OK]   LootShipCount 字段 loot/loot_max/ship/ship_max 齐备')
    except Exception as e:  # noqa: BLE001
        errors.append(f'LootShipCount 字段检查失败: {e}')

    # recognize_loot_count(screen, ocr) -> int | None
    try:
        sig = inspect.signature(recognize_loot_count)
        params = list(sig.parameters.keys())
        if params != ['screen', 'ocr']:
            errors.append(f'recognize_loot_count 签名参数={params}, 期望 [screen, ocr]')
        else:
            print('[OK]   recognize_loot_count(screen, ocr) 签名正确')
    except Exception as e:  # noqa: BLE001
        errors.append(f'recognize_loot_count 签名检查失败: {e}')

    # recognize_ship_count(screen, ocr) -> int | None
    try:
        sig = inspect.signature(recognize_ship_count)
        params = list(sig.parameters.keys())
        if params != ['screen', 'ocr']:
            errors.append(f'recognize_ship_count 签名参数={params}, 期望 [screen, ocr]')
        else:
            print('[OK]   recognize_ship_count(screen, ocr) 签名正确')
    except Exception as e:  # noqa: BLE001
        errors.append(f'recognize_ship_count 签名检查失败: {e}')

    # SortiePanelMixin: enter_sortie / navigate_to_chapter / navigate_to_map /
    #                   recognize_map / get_loot_and_ship_count / click_chapter 必须存在
    required_methods = [
        'enter_sortie',
        'navigate_to_chapter',
        'navigate_to_map',
        'recognize_map',
        'get_loot_and_ship_count',
        'click_chapter',
    ]
    missing_methods = [m for m in required_methods if not hasattr(SortiePanelMixin, m)]
    if missing_methods:
        errors.append(f'SortiePanelMixin 缺方法: {missing_methods}')
    else:
        print('[OK]   SortiePanelMixin 6 个必需方法齐备')

    # enter_sortie 参数: (chapter, map_num)
    try:
        sig = inspect.signature(SortiePanelMixin.enter_sortie)
        params = list(sig.parameters.keys())
        if params != ['self', 'chapter', 'map_num']:
            errors.append(f'enter_sortie 参数={params} != [self,chapter,map_num]')
        else:
            print('[OK]   enter_sortie(self, chapter, map_num) 签名正确')
    except Exception as e:  # noqa: BLE001
        errors.append(f'enter_sortie 签名检查失败: {e}')

    # ── 4. sortie_counters 必须真实导出同名符号（确保真的拆出去了） ──
    try:
        import autowsgr.ui.map.panels.sortie_counters as sc
        required = ('LootShipCount', 'recognize_loot_count', 'recognize_ship_count',
                    'LOOT_MAX', 'SHIP_MAX')
        missing = [s for s in required if not hasattr(sc, s)]
        if missing:
            errors.append(f'sortie_counters 缺符号: {missing}')
        else:
            print('[OK]   sortie_counters 真正导出了 5 个计数器符号')
        # 必须与 sortie.py 重导出的是同一对象（不是重新定义的副本）
        from autowsgr.ui.map.panels import sortie as so
        if sc.LOOT_MAX != so.LOOT_MAX or sc.SHIP_MAX != so.SHIP_MAX:
            errors.append('sortie_counters 的常量值与 sortie.py 不一致')
        if sc.LootShipCount is not so.LootShipCount:
            errors.append('LootShipCount 在 sortie.py 不是 re-export（可能重复定义）')
        if sc.recognize_loot_count is not so.recognize_loot_count:
            errors.append('recognize_loot_count 在 sortie.py 不是 re-export')
        if sc.recognize_ship_count is not so.recognize_ship_count:
            errors.append('recognize_ship_count 在 sortie.py 不是 re-export')
        print('[OK]   sortie.py 的计数器 4 符号均是 sortie_counters 同对象 re-export')
    except ImportError:
        # 第 1 步已经报错，这里不重复
        pass
    except Exception as e:  # noqa: BLE001
        errors.append(f'sortie_counters 内容验证异常: {e}')

    # ── 汇总 ──
    if errors:
        print('\n[FAIL] 共 {} 项不符合契约:'.format(len(errors)))
        for i, e in enumerate(errors, 1):
            print('  {}. {}'.format(i, e))
        return 1
    print('\n[PASS] 所有 API 契约校验通过 ✓')
    return 0


if __name__ == '__main__':
    sys.exit(main())
