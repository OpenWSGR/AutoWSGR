"""模拟器控制器共用的帧标识和采集时间。"""

from __future__ import annotations

from dataclasses import dataclass, replace

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

    def snapshot(self) -> CapturedFrame:
        """保留观察时的像素，防止无解码序号的控制器复用缓冲区。"""
        return self if self.sequence is not None else replace(self, image=self.image.copy())

    def is_newer_than(self, previous: CapturedFrame | None, *, allow_static: bool) -> bool:
        """优先比较解码序号。无序号时，只有允许静态复核才能接受相同像素。"""
        if previous is None:
            return True
        if self.sequence is not None and previous.sequence is not None:
            return self.sequence > previous.sequence
        return self.captured_at > previous.captured_at and (
            allow_static or not np.array_equal(previous.image, self.image)
        )
