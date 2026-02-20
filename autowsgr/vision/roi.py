"""感兴趣区域 (Region of Interest)。

用 4 个浮点参数定义截图中的矩形子区域，限定匹配搜索范围以提升速度和精度。

所有坐标使用相对值 [0.0, 1.0]，与分辨率无关。

使用方式::

    from autowsgr.vision import ROI

    roi = ROI(0.6, 0.8, 1.0, 1.0)       # 右下角
    roi = ROI.from_tuple((0.1, 0.2, 0.5, 0.6))
    roi = ROI.from_dict({"roi": [0.1, 0.2, 0.5, 0.6]})

    cropped = roi.crop(screen)           # 裁切截图
    px1, py1, px2, py2 = roi.to_absolute(960, 540)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class ROI:
    """感兴趣区域 (Region of Interest)。

    用 4 个浮点参数定义截图中的矩形子区域，所有值为相对坐标 [0.0, 1.0]。
    限定搜索范围可以同时提升匹配速度和精度（减少误匹配）。

    Parameters
    ----------
    x1, y1:
        左上角相对坐标。
    x2, y2:
        右下角相对坐标。

    Examples
    --------
    >>> ROI(0.0, 0.0, 1.0, 1.0)  # 全屏
    ROI(x1=0.0, y1=0.0, x2=1.0, y2=1.0)
    >>> ROI(0.6, 0.8, 1.0, 1.0)  # 右下角
    ROI(x1=0.6, y1=0.8, x2=1.0, y2=1.0)
    >>> ROI.from_tuple((0.1, 0.2, 0.5, 0.6))
    ROI(x1=0.1, y1=0.2, x2=0.5, y2=0.6)
    """

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.x1 < self.x2 <= 1.0):
            raise ValueError(
                f"ROI x 坐标无效: x1={self.x1}, x2={self.x2}（需满足 0 ≤ x1 < x2 ≤ 1）"
            )
        if not (0.0 <= self.y1 < self.y2 <= 1.0):
            raise ValueError(
                f"ROI y 坐标无效: y1={self.y1}, y2={self.y2}（需满足 0 ≤ y1 < y2 ≤ 1）"
            )

    # ── 构造 ──

    @classmethod
    def full(cls) -> ROI:
        """全屏 ROI。"""
        return cls(0.0, 0.0, 1.0, 1.0)

    @classmethod
    def from_tuple(cls, t: tuple[float, float, float, float]) -> ROI:
        """从 (x1, y1, x2, y2) 元组创建。"""
        return cls(x1=t[0], y1=t[1], x2=t[2], y2=t[3])

    @classmethod
    def from_dict(cls, d: dict) -> ROI:
        """从字典创建（支持 YAML）。

        字典格式::

            {"x1": 0.6, "y1": 0.8, "x2": 1.0, "y2": 1.0}
            # 或简写
            {"roi": [0.6, 0.8, 1.0, 1.0]}
        """
        if "roi" in d:
            vals = d["roi"]
            return cls(x1=vals[0], y1=vals[1], x2=vals[2], y2=vals[3])
        return cls(
            x1=float(d["x1"]),
            y1=float(d["y1"]),
            x2=float(d["x2"]),
            y2=float(d["y2"]),
        )

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    def to_tuple(self) -> tuple[float, float, float, float]:
        """转为 (x1, y1, x2, y2) 元组。"""
        return (self.x1, self.y1, self.x2, self.y2)

    # ── 变换 ──

    def to_absolute(self, width: int, height: int) -> tuple[int, int, int, int]:
        """转换为绝对像素坐标 (px1, py1, px2, py2)。"""
        return (
            int(self.x1 * width),
            int(self.y1 * height),
            int(self.x2 * width),
            int(self.y2 * height),
        )

    def crop(self, screen: np.ndarray) -> np.ndarray:
        """从截图中裁切出 ROI 区域。

        Parameters
        ----------
        screen:
            原始图像 (H×W×3)。

        Returns
        -------
        np.ndarray
            裁切后的子图像（视图，非拷贝）。
        """
        h, w = screen.shape[:2]
        px1, py1, px2, py2 = self.to_absolute(w, h)
        return screen[py1:py2, px1:px2]

    @property
    def width(self) -> float:
        """ROI 相对宽度。"""
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        """ROI 相对高度。"""
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[float, float]:
        """ROI 相对中心坐标。"""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def contains(self, x: float, y: float) -> bool:
        """判断相对坐标 (x, y) 是否在 ROI 内。"""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def __repr__(self) -> str:
        return f"ROI(x1={self.x1}, y1={self.y1}, x2={self.x2}, y2={self.y2})"
