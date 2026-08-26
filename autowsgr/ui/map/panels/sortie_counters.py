"""出征面板计数器识别 — 战利品/舰船数量 OCR 与数据类。

拆分自 sortie.py 中「纯 OCR + 数据结构」部分，独立文件便于
复用 (campaign.py) 与测试，减少 SortiePanelMixin 体积。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ui.map.data import LOOT_COUNT_CROP, SHIP_COUNT_CROP
from autowsgr.vision import PixelChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.vision import OCREngine


_log = get_logger('ui')

LOOT_MAX = 50
"""战利品 (胖次) 上限, 固定值。"""

SHIP_MAX = 500
"""舰船上限, 固定值。"""


# ── 数据类 ──


@dataclass(frozen=True, slots=True)
class LootShipCount:
    """出征面板右上角的掉落计数。

    Attributes
    ----------
    loot:
        战利品 (胖次) 已获取数量, 识别失败时为 ``None``。
    loot_max:
        战利品上限, 固定 50。
    ship:
        舰船已获取数量, 识别失败时为 ``None``。
    ship_max:
        舰船上限, 固定 500。
    """

    loot: int | None = None
    loot_max: int = LOOT_MAX
    ship: int | None = None
    ship_max: int = SHIP_MAX


# ── 独立识别函数 ──

_OCR_ALLOWLIST = '0123456789/|'
"""OCR 字符白名单。包含 ``/`` 和 ``|`` 使 OCR 正确识别斜线而非误读为 ``1``。"""


def _parse_numerator(text: str, max_val: int) -> int:
    """从 ``"X/Y"`` 格式的 OCR 文本中提取分子 (``/`` 前的数字)。

    - 优先按 ``/`` 或 ``|`` 分割取第一段。
    - 回退: 若无分隔符, 按已知分母剥离末尾后缀。
    """
    # 优先: 按 "/" 或 "|" 分割
    for sep in ('/', '|'):
        if sep in text:
            left = text.split(sep, 1)[0]
            digits = ''.join(c for c in left if c.isdigit())
            if digits:
                return int(digits)
            raise ValueError(f'分子部分无数字: "{text}"')

    # 回退: OCR 偶尔把 "/" 识别为 "1", 导致纯数字串如 "17150"。
    # 已知分母为 max_val, 则后缀为 "1" + str(max_val)。
    digits = ''.join(c for c in text if c.isdigit())
    if not digits:
        raise ValueError(f'文本中无数字: "{text}"')
    suffix = '1' + str(max_val)
    if digits.endswith(suffix) and len(digits) > len(suffix):
        return int(digits[: -len(suffix)])
    # 无 "1" 前缀: 可能分母直接拼接
    denom_str = str(max_val)
    if digits.endswith(denom_str) and len(digits) > len(denom_str):
        return int(digits[: -len(denom_str)])
    return None


def recognize_loot_count(screen: np.ndarray, ocr: OCREngine) -> int | None:
    """识别出征面板战利品 (胖次) 已获取数量。

    OCR ``X/50`` 区域并提取 ``/`` 前的数字, 上限固定为 50。
    """
    img = PixelChecker.crop(screen, *LOOT_COUNT_CROP)
    text = ocr.recognize_single(img, allowlist=_OCR_ALLOWLIST).text.strip()
    if not text:
        _log.warning('[UI] 战利品数量 OCR 无结果')
        return None
    count = _parse_numerator(text, LOOT_MAX)
    if count > 50 and str(count).endswith('1'):
        count = int(str(count)[:-1])  # 可能 OCR 把 "/50" 识别成 "150"
    if count is not None:
        _log.info('[UI] 战利品数量: {}/{}', count, LOOT_MAX)
    else:
        _log.warning("[UI] 战利品数量 OCR 解析失败: '{}'", text)
    return count


def recognize_ship_count(screen: np.ndarray, ocr: OCREngine) -> int | None:
    """识别出征面板舰船已获取数量。

    OCR ``X/500`` 区域并提取 ``/`` 前的数字, 上限固定为 500。
    """
    img = PixelChecker.crop(screen, *SHIP_COUNT_CROP)
    text = ocr.recognize_single(img, allowlist=_OCR_ALLOWLIST).text.strip()
    if not text:
        _log.warning('[UI] 舰船数量 OCR 无结果')
        return None
    count = _parse_numerator(text, SHIP_MAX)
    if count is not None:
        _log.info('[UI] 舰船数量: {}/{}', count, SHIP_MAX)
    else:
        _log.warning("[UI] 舰船数量 OCR 解析失败: '{}'", text)
    return count
