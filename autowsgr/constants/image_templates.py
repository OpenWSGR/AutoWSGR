from functools import partial

from airtest.core.cv import (
    MATCHING_METHODS,
    ST,
    InvalidMatchingMethodError,
    TargetPos,
    Template,
)
from airtest.core.settings import Settings as ST

from autowsgr.constants.data_roots import IMG_ROOT
from autowsgr.utils.io import create_namespace


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
                ret = self._try_match(func, image, screen, threshold=self.threshold, rgb=self.rgb)
            if ret:
                break
        return ret


IMG = create_namespace(IMG_ROOT, partial(MyTemplate, threshold=0.9, resolution=(960, 540)))
