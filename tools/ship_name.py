import easyocr

from autowsgr.utils.io import cv_imread
from autowsgr.utils.operator import unzip_element


ch_reader = None


def load_ch_reader():
    global ch_reader
    ch_reader = easyocr.Reader(['ch_sim'], gpu=True)


def get_allow(names):
    char_set = set()
    for name in unzip_element(names):
        for char in name:
            char_set.add(char)
    res = ''
    for char in char_set:
        res += char
    return res


def recognize(image, char_list=None, min_size=7, text_threshold=0.55, low_text=0.3):
    if ch_reader is None:
        load_ch_reader()
    if isinstance(image, str):
        image = cv_imread(image)
    assert ch_reader is not None
    return ch_reader.readtext(
        image,
        allowlist=char_list,
        min_size=min_size,
        text_threshold=text_threshold,
        low_text=low_text,
    )


if __name__ == '__main__':
    pass
