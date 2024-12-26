from functools import partial

from airtest.core.cv import Template

from autowsgr.constants.data_roots import IMG_ROOT
from autowsgr.utils.io import create_namespace


class MyTemplate(Template):
    def __radd__(self, other) -> list:
        if isinstance(other, list):
            return [*other, self]  # 添加到列表开头
        return NotImplemented

    def __add__(self, other) -> list:
        if isinstance(other, list):
            return [self, *other]  # 添加到列表末尾
        return NotImplemented


IMG = create_namespace(
    IMG_ROOT,
    partial(MyTemplate, threshold=0.9, resolution=(960, 540)),
)
