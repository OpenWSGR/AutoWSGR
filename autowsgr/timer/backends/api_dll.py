import ctypes
from ctypes import POINTER, c_char, c_char_p, c_int32, c_size_t, c_uint8, c_void_p, cast, cdll

import numpy


class ApiDll:
    def __init__(self, path) -> None:
        self.dll = cdll.LoadLibrary(path)
        self.dll.locate.argtypes = c_void_p, POINTER(c_int32 * 100)
        self.dll.locate.restype = c_int32
        self.dll.recognize_enemy.argtypes = (c_void_p, c_char_p)
        self.dll.recognize_enemy.restype = c_int32
        self.dll.recognize_map.argtypes = [c_void_p]
        self.dll.recognize_map.restype = c_char

    def _wrap_img_input(self, image: numpy.ndarray) -> c_void_p:
        arr = c_size_t * 4
        width = c_size_t(image.shape[1])
        height = c_size_t(image.shape[0])
        channels = c_size_t(1) if len(image.shape) == 2 else c_size_t(image.shape[2])
        img = image.astype(numpy.uint8)
        pixels_p = POINTER(c_uint8)
        pixels_p = c_size_t(ctypes.cast(img.ctypes.data_as(pixels_p), c_void_p).value)
        return cast(arr(width, height, channels, pixels_p), c_void_p)

    def _wrap_recognize_enemy_input(self, images: list[c_void_p]) -> c_void_p:
        images_arr = c_void_p * images.__len__()
        arr = images_arr()
        for i in range(images.__len__()):
            arr[i] = ctypes.cast(images[i], c_void_p)
        input_arr = c_void_p * (2)
        return input_arr(images.__len__(), cast(arr, c_void_p))

    def locate(self, image):
        image_p = self._wrap_img_input(image)
        len = c_int32 * 100
        res = len()
        result: c_int32 = self.dll.locate(image_p, ctypes.pointer(res))
        ret: list[tuple] = [(res[i * 2], res[i * 2 + 1]) for i in range(result // 2)]
        return ret

    def recognize_enemy(self, images: list[numpy.ndarray]) -> str:
        images_p = [self._wrap_img_input(image) for image in images]
        input = self._wrap_recognize_enemy_input(images_p)
        ret = ctypes.create_string_buffer(b'\0', 100)
        self.dll.recognize_enemy(input, ret)
        return ret.value.decode('ascii')

    def recognize_map(self, image: list[numpy.ndarray]):
        image_p = self._wrap_img_input(image)
        return chr(self.dll.recognize_map(image_p)[0])
