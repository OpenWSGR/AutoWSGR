"""Shared helpers for vision test modules."""
from __future__ import annotations

import numpy as np

from autowsgr.vision.image_matcher import ImageTemplate


def solid_screen(r: int, g: int, b: int, h: int = 540, w: int = 960) -> np.ndarray:
    """创建纯色截图 (H×W×3, RGB uint8)。"""
    screen = np.zeros((h, w, 3), dtype=np.uint8)
    screen[:, :] = [r, g, b]
    return screen


def make_template(
    seed: int = 42, h: int = 50, w: int = 80, name: str = "test",
) -> ImageTemplate:
    """创建有纹理的随机模板（纯色模板在 TM_CCOEFF_NORMED 下无法正确匹配）。"""
    rng = np.random.RandomState(seed)
    img = rng.randint(0, 256, (h, w, 3), dtype=np.uint8)
    return ImageTemplate(name=name, image=img, source="test")


def embed_template_in_screen(
    screen: np.ndarray,
    template: ImageTemplate,
    x: int,
    y: int,
) -> np.ndarray:
    """将模板嵌入到截图的指定位置 (绝对像素坐标)。"""
    s = screen.copy()
    th, tw = template.shape
    s[y : y + th, x : x + tw] = template.image
    return s
