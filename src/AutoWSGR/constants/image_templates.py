import os
import re

from airtest.core.cv import (
    MATCHING_METHODS,
    ST,
    InvalidMatchingMethodError,
    TargetPos,
    Template,
)
from airtest.core.settings import Settings as ST

from .data_roots import IMG_ROOT


class MyTemplate(Template):
    def match_in(self, screen, this_methods=None):
        match_result = self._cv_match(screen, this_methods)
        if not match_result:
            return None
        focus_pos = TargetPos().getXY(match_result, self.target_pos)
        return focus_pos

    def _cv_match(self, screen, this_methods=None):
        ori_image = self._imread()
        image = self._resize_image(ori_image, screen, ST.RESIZE_METHOD)
        ret = None
        if this_methods is None:
            this_methods = ST.CVSTRATEGY
        for method in this_methods:
            # get function definition and execute:
            func = MATCHING_METHODS.get(method, None)
            if func is None:
                raise InvalidMatchingMethodError(
                    f"Undefined method in CVSTRATEGY: '{method}', try 'kaze'/'brisk'/'akaze'/'orb'/'surf'/'sift'/'brief' instead."
                )
            if method in ["mstpl", "gmstpl"]:
                ret = self._try_match(
                    func,
                    ori_image,
                    screen,
                    threshold=self.threshold,
                    rgb=self.rgb,
                    record_pos=self.record_pos,
                    resolution=self.resolution,
                    scale_max=self.scale_max,
                    scale_step=self.scale_step,
                )
            else:
                ret = self._try_match(
                    func, image, screen, threshold=self.threshold, rgb=self.rgb
                )
            if ret:
                break
        return ret


def make_dir_templates(path):
    """建立 path 目录下所有图片的模板字典"""
    # 不处理二级目录和非 .png 文件
    all_files = [
        file
        for file in os.listdir(path)
        if not (os.path.isdir(file or file.split(".")[-1].lower() != "png"))
    ]

    if all(file.split(".")[0].isdecimal() for file in all_files):
        res = [
            None,
        ]
        for file in all_files:
            key = int(file.split(".")[0])
            if key >= len(res):
                res.extend(
                    [
                        None,
                    ]
                    * (key - len(res) + 1)
                )
            file_path = os.path.join(path, file)
            res[key] = MyTemplate(file_path, 0.9, resolution=(960, 540))
    else:
        res = {}
        for file in all_files:
            file_path = os.path.join(path, file)
            key_name = file.split(".")[0]
            if key_name.isdecimal():
                res[int(key_name)] = MyTemplate(file_path, 0.9, resolution=(960, 540))
            res[key_name] = MyTemplate(file_path, 0.9, resolution=(960, 540))

    return res


def make_dir_templates_without_number(path):
    """给定路径, 返回一个字典

    字典的键为路径下所有图片的英文字母文件名(不含后缀)

    字典的值为对应图片的 MyTemplate 类列表, 所有英文名相同的图片会被放入同一个列表(仅忽略数字)
    """
    res = {}
    for file in os.listdir(path):
        filename = file.split(".")[0]
        key_name = re.findall(r"[^0-9]*", filename)[0]
        if key_name not in res.keys():
            res[key_name] = []
        file_path = os.path.join(path, file)
        res[key_name].append(MyTemplate(file_path, 0.9, resolution=(960, 540)))
    return res


class ImageSet:
    def __init__(self):
        # identify_images 多图识别，单独处理
        self.identify_images = make_dir_templates_without_number(
            f"{IMG_ROOT}/identify_images"
        )

        for sub_folder in os.listdir(IMG_ROOT):
            if sub_folder not in self.__dict__:
                sub_folder_path = os.path.join(IMG_ROOT, sub_folder)
                self.__dict__.update({sub_folder: make_dir_templates(sub_folder_path)})


IMG = ImageSet()
