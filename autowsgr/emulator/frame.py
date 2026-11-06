"""模拟器控制器共用的帧标识和采集时间。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """包含可选解码序号和单调采集时间的 RGB 图像。

    相同序号代表同一张解码图像，即使调用者重复读取也不改变其身份。
    序号为 None 表示控制器无法提供帧标识，调用者不能把重复截图视为独立证据。
    """

    image: np.ndarray
    sequence: int | None
    captured_at: float
