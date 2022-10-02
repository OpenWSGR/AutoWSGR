import os
import re

from airtest.core.cv import (MATCHING_METHODS, ST, InvalidMatchingMethodError,
                             TargetPos, Template)
from airtest.core.helper import G
from airtest.core.settings import Settings as ST
from AutoWSGR.utils.io import (all_in, get_all_files, get_file_suffixname,
                               listdir)

from .data_roots import IMG_ROOT
from .other_constants import ALL_ERRORS, ALL_PAGES, FIGHT_RESULTS

all_images = get_all_files(IMG_ROOT)


class MyTemplate(Template):
    def match_in(self, screen, this_methods=None):
        match_result = self._cv_match(screen, this_methods)
        G.LOGGING.debug("match result: %s", match_result)
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
                    "Undefined method in CVSTRATEGY: '%s', try 'kaze'/'brisk'/'akaze'/'orb'/'surf'/'sift'/'brief' instead." % method)
            if method in ["mstpl", "gmstpl"]:
                ret = self._try_match(func, ori_image, screen, threshold=self.threshold, rgb=self.rgb, record_pos=self.record_pos,
                                      resolution=self.resolution, scale_max=self.scale_max, scale_step=self.scale_step)
            else:
                ret = self._try_match(func, image, screen, threshold=self.threshold, rgb=self.rgb)
            if ret:
                break
        return ret


def make_dir_templates(path):
    """给定路径,返回一个字典    

    字典的键为路径下所有图片的文件名(不含后缀)

    字典的值为对应图片的 MyTemplate 类

    如果文件名是纯数字,再创建一个数字下标映射
    """
    res = {}
    files = listdir(path)
    for file in files:
        if (os.path.isdir(file) or get_file_suffixname(file) != "PNG"):
            continue
        filename = os.path.basename(file).split('.')[0]
        res[filename] = make_tmplate(path=file)[0]
        if (filename.isdecimal()):
            res[int(filename)] = make_tmplate(path=file)[0]
    return res


def make_dir_templates_without_number(path):
    """给定路径,返回一个字典    

    字典的键为路径下所有图片的英文字母文件名(不含后缀)

    字典的值为对应图片的 MyTemplate 类列表,所有英文名相同的图片会被放入同一个列表(仅忽略数字)
    """
    files = listdir(path)
    res = {}
    for file in files:
        filename = os.path.basename(file).split('.')[0]
        alpha = re.findall(r'[^0-9]*', filename)[0]
        if (alpha not in res.keys()):
            res[alpha] = []
        res[alpha] += make_tmplate(path=file)
    return res


def make_tmplate(name=None, path=None, all_image=all_images, *args, **kwargs):
    """给定路径，或者给定关键字和图片库返回一个图像模板列表。

    Args:
        name (list): 关键字组

    Returns:
        如果给定了关键字和图像列表，则返回图像列表中，路径字符串含关键字的图片列表

        否则返回给定路径的图片模板,(单个元素以列表形式)
    """
    if (name is not None):
        if (not isinstance(name, list)):
            name = [name]
        rec_pos = kwargs['rec_pos'] if "rec_pos" in kwargs else None
        return [MyTemplate(image, 0.9, resolution=(960, 540), record_pos=rec_pos) for image in all_image if (all_in(name, image))]

    return [MyTemplate(path, 0.9, resolution=(960, 540))]


class ImageSet():
    def __init__(self):
        self.fight_result_image = {}
        for result in FIGHT_RESULTS:
            self.fight_result_image[result] = make_tmplate(path=f'{IMG_ROOT}/fight_result/{result}.PNG')


        self.exercise_image = {'rival_info': make_tmplate(path=f'{IMG_ROOT}/exercise/rival_info.PNG')}

        self.error_image = {}
        for error in ALL_ERRORS:
            self.error_image[error] = make_tmplate(name=error)

        self.identify_images = {}
        for page in ALL_PAGES:
            self.identify_images[page] = make_tmplate(name=page)

        for sub_folder in os.listdir(IMG_ROOT):
            if sub_folder not in ["identify_images", "errors", "fight_result", "exercise"]:
                if not hasattr(self, sub_folder):
                    exec(f"self.{sub_folder} = ['', ]")
                for i in range(1, 1 + len(os.listdir(os.path.join(IMG_ROOT, sub_folder)))):
                    eval(f"self.{sub_folder}").append(
                        MyTemplate(os.path.join(IMG_ROOT, sub_folder, f"{i}.PNG"), resolution=(960, 540)))


IMG = ImageSet()
