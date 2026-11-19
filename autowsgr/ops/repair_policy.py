"""按可验证的伤情和时长判断维修方式。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum


BLIND_RECHECK_SECONDS = 180


class RepairAction(StrEnum):
    NONE = 'none'
    QUICK = 'quick'
    BATH = 'bath'
    WAIT = 'wait'
    RECHECK = 'recheck'


@dataclass(frozen=True, slots=True)
class RepairDecision:
    action: RepairAction
    wait_seconds: float | None = None


def parse_repair_duration(value: str) -> int | None:
    """读取完整的时分秒，保留实际读出的零秒。"""
    match = re.fullmatch(r'(\d+):([0-5]\d):([0-5]\d)', value.strip())
    if match is None:
        return None
    hours, minutes, seconds = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _validate_duration(value: float | None, name: str) -> None:
    if value is not None and (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f'{name} 必须是非负有限秒数或留空')


def decide_repair(
    *,
    required: bool | None,
    repairing: bool | None,
    repair_seconds: float | None,
    quick_threshold_seconds: float | None,
) -> RepairDecision:
    """将长修列为快修候选、短修列为入浴目标。计时到期需重新观察。"""
    _validate_duration(repair_seconds, 'repair_seconds')
    _validate_duration(quick_threshold_seconds, 'quick_threshold_seconds')
    if any(value is not None and type(value) is not bool for value in (required, repairing)):
        raise TypeError('需修、在修标志必须为布尔值或留空')
    if repairing is True:
        if repair_seconds is None:
            return RepairDecision(RepairAction.WAIT, BLIND_RECHECK_SECONDS)
        if repair_seconds is not None and repair_seconds > 0:
            return RepairDecision(RepairAction.WAIT, float(repair_seconds))
        return RepairDecision(RepairAction.RECHECK)
    if repairing is False and required is False:
        return RepairDecision(RepairAction.NONE)
    if (
        repairing is False
        and required is True
        and repair_seconds is not None
        and quick_threshold_seconds is not None
    ):
        action = (
            RepairAction.QUICK if repair_seconds >= quick_threshold_seconds else RepairAction.BATH
        )
        return RepairDecision(action)
    return RepairDecision(RepairAction.RECHECK)
