"""C++ DLL 图像识别接口包装。

移植自旧代码 ``timer/backends/api_dll.py``，提供三个函数:

- :func:`ApiDll.locate` — 定位截图中舰船名称所在行区域
- :func:`ApiDll.recognize_enemy` — 识别 6 张敌方舰类缩略图
- :func:`ApiDll.recognize_map` — 识别决战地图节点字母

DLL 二进制位于 ``autowsgr/data/bin/{platform}_image_autowsgrs.bin``。
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import (
    POINTER,
    c_char,
    c_char_p,
    c_int32,
    c_size_t,
    c_uint8,
    c_void_p,
    cast,
    cdll,
)
from pathlib import Path

import numpy as np
from loguru import logger

# DLL 所在目录 — autowsgr/data/bin/
_BIN_DIR = Path(__file__).resolve().parent.parent / "data" / "bin"


class ApiDll:
    """C++ 图像识别 DLL 包装器。

    Parameters
    ----------
    bin_dir:
        DLL 二进制所在目录，默认 ``autowsgr/data/bin/``。
    """

    def __init__(self, bin_dir: str | Path | None = None) -> None:
        bin_dir = Path(bin_dir) if bin_dir else _BIN_DIR
        dll_name = f"{sys.platform}_image_autowsgrs.bin"
        dll_path = bin_dir / dll_name

        if not dll_path.exists():
            raise FileNotFoundError(
                f"找不到 DLL: {dll_path}\n"
                f"当前平台: {sys.platform}，"
                f"可用文件: {list(bin_dir.glob('*.bin'))}"
            )

        logger.info("[DLL] 加载: {}", dll_path)
        self._dll = cdll.LoadLibrary(str(dll_path))

        # 设置函数签名
        self._dll.locate.argtypes = [c_void_p, POINTER(c_int32 * 100)]
        self._dll.locate.restype = c_int32

        self._dll.recognize_enemy.argtypes = [c_void_p, c_char_p]
        self._dll.recognize_enemy.restype = c_int32

        self._dll.recognize_map.argtypes = [c_void_p]
        self._dll.recognize_map.restype = c_char

    # ── 公共接口 ──

    def locate(self, image: np.ndarray) -> list[tuple[int, int]]:
        """定位图像中舰船名称所在行的 (row_start, row_end) 坐标对。

        用于 ``recognize_ship``: 先定位行区域，再对每行做 OCR。

        Parameters
        ----------
        image:
            灰度或彩色图像。

        Returns
        -------
        list[tuple[int, int]]
            ``(row_start, row_end)`` 列表。
        """
        image_p = self._wrap_img_input(image)
        buf_type = c_int32 * 100
        buf = buf_type()
        count: int = self._dll.locate(image_p, ctypes.pointer(buf))
        return [(buf[i * 2], buf[i * 2 + 1]) for i in range(count // 2)]

    def recognize_enemy(self, images: list[np.ndarray]) -> str:
        """识别敌方舰船类型。

        传入 6 张裁剪好的舰类缩略图（灰度），
        返回空格分隔的类型字符串，如 ``"DD CL CA BB CV SS"``。

        Parameters
        ----------
        images:
            6 张裁剪后的灰度缩略图。

        Returns
        -------
        str
            空格分隔的舰类缩写。
        """
        images_p = [self._wrap_img_input(img) for img in images]
        input_p = self._wrap_recognize_enemy_input(images_p)
        ret = ctypes.create_string_buffer(b"\0", 100)
        self._dll.recognize_enemy(input_p, ret)
        return ret.value.decode("ascii")

    def recognize_map(self, image: np.ndarray) -> str:
        """识别决战地图节点。

        传入裁剪的地图节点列图像（彩色/灰度），返回节点字母。

        Parameters
        ----------
        image:
            包含节点字母的裁剪图像。

        Returns
        -------
        str
            节点字母（如 ``'A'``, ``'B'``），失败时返回 ``'0'``。
        """
        image_p = self._wrap_img_input(image)
        result = self._dll.recognize_map(image_p)
        return chr(result[0])

    # ── 内部方法 ──

    @staticmethod
    def _wrap_img_input(image: np.ndarray) -> c_void_p:
        """将 numpy 图像包装为 DLL 输入结构。"""
        arr = c_size_t * 4
        width = c_size_t(image.shape[1])
        height = c_size_t(image.shape[0])
        channels = c_size_t(1) if len(image.shape) == 2 else c_size_t(image.shape[2])
        img = image.astype(np.uint8)
        pixels_p = POINTER(c_uint8)
        pixels_p = c_size_t(
            ctypes.cast(img.ctypes.data_as(pixels_p), c_void_p).value
        )
        return cast(arr(width, height, channels, pixels_p), c_void_p)

    @staticmethod
    def _wrap_recognize_enemy_input(images: list[c_void_p]) -> c_void_p:
        """将多张图像指针包装为 DLL 的 recognize_enemy 输入。"""
        images_arr = c_void_p * len(images)
        arr = images_arr()
        for i in range(len(images)):
            arr[i] = ctypes.cast(images[i], c_void_p)
        input_arr = c_void_p * 2
        return input_arr(len(images), cast(arr, c_void_p))


# ── 单例 ──

_dll_instance: ApiDll | None = None


def get_api_dll() -> ApiDll:
    """获取 ApiDll 单例。首次调用时加载 DLL。"""
    global _dll_instance
    if _dll_instance is None:
        _dll_instance = ApiDll()
    return _dll_instance
