import autowsgr_native
import cv2
import numpy as np


_TARGET_H = 720


class ApiDll:
    def locate(self, image: np.ndarray):
        return autowsgr_native.locate(image)

    def recognize_enemy(self, images: list[np.ndarray]) -> str:
        return autowsgr_native.recognize_enemy(images)

    def recognize_map(self, image: np.ndarray):
        h, w = image.shape[:2]
        if h > _TARGET_H:
            scale = _TARGET_H / h
            image = cv2.resize(
                image,
                (int(w * scale), _TARGET_H),
                interpolation=cv2.INTER_LINEAR if scale > 1 else cv2.INTER_AREA,
            )
        return autowsgr_native.recognize_map(image)


_dll_instance: ApiDll | None = None


def get_api_dll() -> ApiDll:
    """获取 ApiDll 单例。首次调用时加载 DLL。"""
    global _dll_instance
    if _dll_instance is None:
        _dll_instance = ApiDll()
    return _dll_instance
