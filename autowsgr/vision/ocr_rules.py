"""舰船 OCR 特殊规则。

本文件只保存能够明确解释、能够单独测试的 OCR 规则。
不要在这里加入页面坐标、点击流程、舰队槽位或 EasyOCR 调用。

手动增加规则时按以下方式处理：

1. 系统舰名误识别：在 ``SHIP_NAME_CORRECTIONS`` 中增加
   ``'OCR 原文': '标准舰名'``，并为该原文补充单元测试。
2. 用户舰名误识别：在 ``usersettings.yaml`` 的
   ``ocr.ship_name_corrections`` 中增加 ``OCR 原文: 标准舰名``。
   目标不在 ``SHIPNAMES`` 时会记录警告并跳过，不影响程序启动。
3. 用户舰名别名：在 ``ocr.ship_name_aliases`` 中增加
   ``用户自定义名: 标准舰名``，自定义名会加入标准舰名所属的
   ``No.xxx`` 同船名称列表。
4. 特殊分隔符：只在有实机日志证明某个符号被稳定误读时，
   增加一个范围明确的正则；不要统一删除 ``/``、``-``、``·``。
5. 舰名后缀：统一由 ``autowsgr.constants.normalize_ship_name`` 处理。
   修改规则时必须补充真实舰名不受影响的测试。
6. 等级字符：在 ``LEVEL_DIGIT_TRANSLATION`` 中增加
   ``'OCR 字符': '数字'``，并把该字符加入 ``LEVEL_OCR_ALLOWLIST``；
   右侧必须是单个十进制数字。
7. 舰船等级范围固定为 1-110，不通过新增规则放宽上限。
8. OCR 引擎参数统一登记到对应的 Profile 映射，调用方不直接传底层参数。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from autowsgr.constants import (
    expand_ship_name_candidates as expand_group_candidates,
)
from autowsgr.constants import get_ship_name_group_id, set_ship_name_aliases
from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipType


if TYPE_CHECKING:
    from collections.abc import Mapping


_log = get_logger('vision.ocr')


class EasyOCRProfile(StrEnum):
    """EasyOCR 单行识别参数配置档案。"""

    DEFAULT = 'default'
    FLEET_SHIP_LEVEL = 'fleet_ship_level'
    SHIP_POOL_LEVEL = 'ship_pool_level'
    SHIP_POOL_TYPE = 'ship_pool_type'


@dataclass(frozen=True, slots=True)
class EasyOCRParams:
    """一组集中维护的 EasyOCR 单行识别参数。"""

    allowlist: str = ''
    decoder: str = 'greedy'
    contrast_ths: float = 1.0
    adjust_contrast: float = 1.0


class FastOCRProfile(StrEnum):
    """FastOCR 识别模式配置档案。"""

    DEFAULT = 'default'
    SINGLE_LINE = 'single_line'


@dataclass(frozen=True, slots=True)
class FastOCRParams:
    """一组集中维护的 FastOCR 识别参数。"""

    only_rec: bool = False


# 系统规则由项目维护，目标必须是 shipnames.yaml 中的标准舰名。
SHIP_NAME_CORRECTIONS: dict[str, str] = {
    '鲍鱼': '鲃鱼',
    '鳟盹': '鳞鲀',
    '296': 'M-296',
    '维内托': '维托里奥·维内托',
    'IA': 'IIIA',
}

# 用户规则在启动时从 OCRConfig 加载，不修改系统规则。
_USER_SHIP_NAME_CORRECTIONS: dict[str, str] = {}
_USER_SHIP_NAME_ALIASES: dict[str, str] = {}

# EasyOCR 会把中文舰名中的间隔号识别成冒号，只修正两个汉字之间的冒号。
_CJK_COLON_SEPARATOR_RE = re.compile(r'(?<=[\u3400-\u9fff]):(?=[\u3400-\u9fff])')

SHIP_LEVEL_MIN = 1
SHIP_LEVEL_MAX = 110

# 两种等级 OCR 引擎共用该字符集，识别后再统一纠错。
LEVEL_OCR_ALLOWLIST = '0123456789ILilOoDdSsBbVvYy.:'
LEVEL_DIGIT_CONFUSABLES = 'ILilOoDdSsBb'
SHIP_TYPE_OCR_ALLOWLIST = ''.join(
    dict.fromkeys(ship_type.value for ship_type in ShipType if ship_type is not ShipType.Other),
)

_EASY_OCR_PARAMS_BY_PROFILE: dict[EasyOCRProfile, EasyOCRParams] = {
    EasyOCRProfile.DEFAULT: EasyOCRParams(),
    EasyOCRProfile.FLEET_SHIP_LEVEL: EasyOCRParams(allowlist=LEVEL_OCR_ALLOWLIST),
    EasyOCRProfile.SHIP_POOL_LEVEL: EasyOCRParams(allowlist=LEVEL_OCR_ALLOWLIST),
    EasyOCRProfile.SHIP_POOL_TYPE: EasyOCRParams(allowlist=SHIP_TYPE_OCR_ALLOWLIST),
}

_FAST_OCR_PARAMS_BY_PROFILE: dict[FastOCRProfile, FastOCRParams] = {
    FastOCRProfile.DEFAULT: FastOCRParams(),
    FastOCRProfile.SINGLE_LINE: FastOCRParams(only_rec=True),
}


def get_easyocr_params(profile: EasyOCRProfile | str) -> EasyOCRParams:
    """根据调用场景配置档案返回 EasyOCR 参数。"""
    try:
        normalized_profile = EasyOCRProfile(profile)
    except ValueError as exc:
        raise ValueError(f'未知的 EasyOCR 参数配置档案: {profile}') from exc
    return _EASY_OCR_PARAMS_BY_PROFILE[normalized_profile]


def get_fastocr_params(profile: FastOCRProfile | str) -> FastOCRParams:
    """根据调用场景配置档案返回 FastOCR 参数。"""
    try:
        normalized_profile = FastOCRProfile(profile)
    except ValueError as exc:
        raise ValueError(f'未知的 FastOCR 参数配置档案: {profile}') from exc
    return _FAST_OCR_PARAMS_BY_PROFILE[normalized_profile]


# 等级数字的易混淆字符；新增项时右侧只能是一个数字。
LEVEL_DIGIT_TRANSLATION = str.maketrans(
    {
        'I': '1',
        'i': '1',
        'l': '1',
        'L': '1',
        'O': '0',
        'o': '0',
        'D': '0',
        'd': '0',
        'S': '5',
        's': '5',
        'B': '8',
        'b': '8',
    },
)

# ``Lv.`` 标签和等级数字可能在紧凑区域中被 EasyOCR 拆成两个文本框。
LEVEL_PATTERN = re.compile(r'[Ll][Vv]\.?\s*([0-9ILilOoDdSsBb]{1,6})')
LEVEL_NOISY_PATTERN = re.compile(
    r'(?:[LlIi1O0][VvYy1Ii])[\.:]?\s*([0-9ILilOoDdSsBb]{1,6})',
)
# EasyOCR 在极窄等级区域中偶尔只保留 ``L.``，丢失中间的 ``V``。
LEVEL_SHORT_PATTERN = re.compile(r'[Ll][\.:]?\s*([0-9ILilOoDdSsBb]{1,6})')


def set_user_ship_name_corrections(corrections: Mapping[str, str]) -> int:
    """加载有效用户规则，跳过目标不在 SHIPNAMES 中的条目。"""
    from autowsgr.constants import SHIPNAMES

    valid_names = set(SHIPNAMES)
    loaded: dict[str, str] = {}
    for raw_text, ship_name in corrections.items():
        if ship_name not in valid_names:
            _log.warning(
                "[OCR] 用户舰名规则目标 '{}' 不在 SHIPNAMES，已跳过: '{}'",
                ship_name,
                raw_text,
            )
            continue
        loaded[raw_text] = ship_name

    _USER_SHIP_NAME_CORRECTIONS.clear()
    _USER_SHIP_NAME_CORRECTIONS.update(loaded)
    return len(loaded)


def set_user_ship_name_aliases(aliases: Mapping[str, str]) -> int:
    """加载用户舰名别名，跳过标准名错误或重复登记的条目。"""
    from autowsgr.constants import SHIPNAMES

    set_ship_name_aliases({})
    valid_names = set(SHIPNAMES)
    loaded: dict[str, str] = {}
    for alias, ship_name in aliases.items():
        if ship_name not in valid_names or get_ship_name_group_id(ship_name) is None:
            _log.warning(
                "[OCR] 用户舰名别名目标 '{}' 不在 SHIPNAMES，已跳过: '{}'",
                ship_name,
                alias,
            )
            continue
        if alias in valid_names:
            _log.warning("[OCR] 用户舰名别名 '{}' 已是标准舰名，已跳过", alias)
            continue
        loaded[alias] = ship_name

    set_ship_name_aliases(loaded)
    _USER_SHIP_NAME_ALIASES.clear()
    _USER_SHIP_NAME_ALIASES.update(loaded)
    return len(loaded)


def expand_ship_name_candidates(candidates: list[str]) -> list[str]:
    """将当前舰名候选扩展为同组全部名称。"""
    return expand_group_candidates(candidates)


def apply_ship_name_rules(text: str) -> str:
    """依次应用 OCR 纠错和特殊字符规则。"""
    for corrections in (_USER_SHIP_NAME_CORRECTIONS, SHIP_NAME_CORRECTIONS):
        for old, new in corrections.items():
            if old in text:
                return new

    # 潜艇名的 U 常被识别成 0，例如 U-1206 -> 01206。
    if text.startswith('0') and sum(char.isdigit() for char in text) >= 3:
        text = 'U' + text[1:]

    text = _CJK_COLON_SEPARATOR_RE.sub('·', text)
    return text


def normalize_level_digits(raw_digits: str) -> str | None:
    """将等级易混淆字符转成数字；包含其他字符时拒绝解析。"""
    normalized = raw_digits.translate(LEVEL_DIGIT_TRANSLATION)
    if not normalized or not normalized.isascii() or not normalized.isdigit():
        return None
    return normalized


def is_valid_ship_level(value: int) -> bool:
    """判断数字是否位于游戏当前允许的舰船等级范围。"""
    return SHIP_LEVEL_MIN <= value <= SHIP_LEVEL_MAX
