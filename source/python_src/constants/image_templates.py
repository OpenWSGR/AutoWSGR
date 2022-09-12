import os
from types import SimpleNamespace
from airtest.core.cv import (MATCHING_METHODS, ST, InvalidMatchingMethodError,
                             TargetPos, Template)
from airtest.core.helper import G
from airtest.core.settings import Settings as ST
from utils.io import get_all_files

from .other_constants import ALL_PAGES, ALL_ERRORS, FIGHT_RESULTS
all_images = get_all_files('./data/images')


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
            else:
                if method in ["mstpl", "gmstpl"]:
                    ret = self._try_match(func, ori_image, screen, threshold=self.threshold, rgb=self.rgb, record_pos=self.record_pos,
                                          resolution=self.resolution, scale_max=self.scale_max, scale_step=self.scale_step)
                else:
                    ret = self._try_match(func, image, screen, threshold=self.threshold, rgb=self.rgb)
            if ret:
                break
        return ret


def make_tmplate(name=None, path=None, *args, **kwargs):
    if (name is not None):
        rec_pos = kwargs['rec_pos'] if "rec_pos" in kwargs else None
        return [MyTemplate(image, 0.9, resolution=(960, 540), record_pos=rec_pos) for image in all_images if (name in image)]

    return [MyTemplate(path, 0.9, resolution=(960, 540))]


class ImageSet():
    def __init__(self):
        self.fight_result_image = {}
        for result in FIGHT_RESULTS:
            self.fight_result_image[result] = make_tmplate(path='data/images/fight_result/' + result + '.PNG')

        self.exercise_image = {'rival_info': make_tmplate(path='data/images/exercise/rival_info.PNG')}
        
        self.error_image = {}
        for error in ALL_ERRORS:
            self.error_image[error] = make_tmplate(name=error)
        
        self.identify_images = {}
        for page in ALL_PAGES:
            self.identify_images[page] = make_tmplate(name=page)
        
        PrePath = "./data/images/"
        for sub_folder in os.listdir(PrePath):
            if sub_folder not in ["identify_images", "errors", "fight_result", "exercise"]:
                if not hasattr(self, sub_folder):
                    exec(f"self.{sub_folder} = ['', ]")
                for i in range(1, 1 + len(os.listdir(os.path.join(PrePath, sub_folder)))):
                    eval(f"self.{sub_folder}").append(
                        MyTemplate(os.path.join(PrePath, sub_folder, f"{i}.PNG"), resolution=(960, 540)))


IMG = ImageSet()
