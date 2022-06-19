if(__name__ == '__main__'):
    path = './source/python/rewrite'
    import os
    import sys
    print(os.path.abspath(path))
    sys.path.append(os.path.abspath(path))

from supports import *
from api import *

__all__ = ["identify_page", "wait_pages", "get_now_page", "check_now_page"]


def intergrative_page_identify(timer: Timer):
    positions = [(171, 47), (300, 47), (393, 47), (504, 47), (659, 47)]
    for i, position in enumerate(positions):
        if(PixelChecker(timer, position, (225, 130, 16))):
            return i + 1


@logit_time()
def identify_page(timer: Timer, name, need_screen_shot=1):
    if(need_screen_shot):
        UpdateScreen(timer)

    if (name == 'main_page') and (identify_page(timer, 'options_page', 0)):
        return False
    if (name == 'map_page') and ((intergrative_page_identify(timer) != 1 or PixelChecker(timer, (35, 297), (47, 253, 226)))):
        return False
    if (name == 'build_page') and (intergrative_page_identify(timer) != 1):
        return False
    if (name == 'develop_page') and (intergrative_page_identify(timer) != 3):
        return False

    for template in identify_images[name]:
        if(ImagesExist(timer, template, 0)):
            return True
    return False


@logit_time()
def wait_pages(timer: Timer, names, timeout=5, gap=.1):
    start_time = time.time()
    if(isinstance(names, str)):
        names = [names]
    while(True):
        UpdateScreen(timer)
        for i, name in enumerate(names):
            if(identify_page(timer, name, 0)):
                return i + 1

        if(time.time() - start_time > timeout):
            break
        time.sleep(gap)

    raise TimeoutError("identify timeout of" + str(names))


@logit_time()
def get_now_page(timer: Timer):
    for page in ALL_UI:
        if(identify_page(timer, page, no_log=True)):
            return page


@logit_time()
def check_now_page(timer: Timer):
    return identify_page(timer, name=timer.now_page.name, no_log=True)
