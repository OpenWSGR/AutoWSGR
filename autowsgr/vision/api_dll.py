from functools import lru_cache

import cv2
import numpy as np
from autowsgr_native.recognition import locate, recognize_enemy, recognize_map


_TARGET_H = 720


class ApiDll:
    def locate(self, image: np.ndarray) -> list[list[int]]:
        return locate(image)

    def recognize_enemy(self, images: list[np.ndarray]) -> str:
        return recognize_enemy(images)

    def recognize_map(self, image: np.ndarray) -> str:
        h, w = image.shape[:2]
        if h > _TARGET_H:
            scale = _TARGET_H / h
            image = cv2.resize(
                image,
                (int(w * scale), _TARGET_H),
                interpolation=cv2.INTER_LINEAR if scale > 1 else cv2.INTER_AREA,
            )
        return recognize_map(image.astype(np.uint8))


@lru_cache(maxsize=1)
def get_api_dll() -> ApiDll:
    """获取 ApiDll 单例。首次调用时加载 DLL。"""
    return ApiDll()
