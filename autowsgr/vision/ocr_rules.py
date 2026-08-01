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
5. 舰名后缀：在 ``SHIP_NAME_SUFFIXES`` 中增加完整后缀，
   或增加只匹配末尾的正则，同时补充真实舰名不受影响的测试。
6. 等级字符：在 ``LEVEL_DIGIT_TRANSLATION`` 中增加
   ``'OCR 字符': '数字'``；右侧必须是单个十进制数字。
7. 舰船等级范围固定为 1-110，不通过新增规则放宽上限。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from autowsgr.constants import (
    canonical_ship_name,
    get_ship_name_group_id,
    set_ship_name_aliases,
)
from autowsgr.constants import (
    expand_ship_name_candidates as expand_group_candidates,
)
from autowsgr.infra.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Mapping


_log = get_logger('vision.ocr')

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

# 只处理已确认的完整后缀，不删除舰名中间的间隔号。
SHIP_NAME_SUFFIXES: tuple[str, ...] = ('·改',)

# 处理舰名末尾由括号包围的别名，例如“岛风（苍青幻影）”。
SHIP_ALIAS_SUFFIX_RE = re.compile(r'\s*[（(][^（）()]*[)）]\s*$')

# EasyOCR 会把中文舰名中的间隔号识别成冒号，只修正两个汉字之间的冒号。
_CJK_COLON_SEPARATOR_RE = re.compile(r'(?<=[\u3400-\u9fff]):(?=[\u3400-\u9fff])')

SHIP_LEVEL_MIN = 1
SHIP_LEVEL_MAX = 110

# 等级数字的易混淆字符；新增项时右侧只能是一个数字。
LEVEL_DIGIT_TRANSLATION = str.maketrans(
    {
        'I': '1',
        'i': '1',
        'l': '1',
        'L': '1',
        'O': '0',
        'o': '0',
    },
)

# ``Lv.`` 标签和等级数字可能在紧凑区域中被 EasyOCR 拆成两个文本框。
LEVEL_PATTERN = re.compile(r'[Ll][Vv]\.?\s*([0-9ILilOo]{1,6})')
LEVEL_NOISY_PATTERN = re.compile(r'(?:[LlIi1O0][VvYy])[\.:]?\s*([0-9ILilOo]{1,6})')
LEVEL_LABEL_PATTERN = re.compile(r'[LlIi1O0][VvYy]')


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


def resolve_ship_name_alias(text: str) -> str:
    """将用户补充的显示名转换为 SHIPNAMES 标准舰名。"""
    return canonical_ship_name(text.strip())


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


def normalize_ship_name_suffix(text: str) -> str:
    """去掉明确登记的舰名尾部标记，保留舰名内部特殊字符。"""
    normalized = resolve_ship_name_alias(text)
    for suffix in SHIP_NAME_SUFFIXES:
        normalized = normalized.removesuffix(suffix)
    return SHIP_ALIAS_SUFFIX_RE.sub('', normalized).strip()


def normalize_level_digits(raw_digits: str) -> str | None:
    """将等级易混淆字符转成数字；包含其他字符时拒绝解析。"""
    normalized = raw_digits.translate(LEVEL_DIGIT_TRANSLATION)
    if not normalized or not normalized.isascii() or not normalized.isdigit():
        return None
    return normalized


def is_valid_ship_level(value: int) -> bool:
    """判断数字是否位于游戏当前允许的舰船等级范围。"""
    return SHIP_LEVEL_MIN <= value <= SHIP_LEVEL_MAX
