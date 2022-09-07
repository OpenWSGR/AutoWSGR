import time

from utils.api_android import UpdateScreen
from utils.api_image import ImagesExist, PixelChecker
from constants.image_templates import IdentifyImages
from constants.other_constants import ALL_UI, INFO1
from utils.logger import logit
from timer.run_timer import Timer


@logit()
def intergrative_page_identify(timer: Timer):
    positions = [(171, 47), (300, 47), (393, 47), (504, 47), (659, 47)]
    for i, position in enumerate(positions):
        if (PixelChecker(timer, position, (225, 130, 16))):
            return i + 1


@logit()
def identify_page(timer: Timer, name, need_screen_shot=True):
    if need_screen_shot:
        UpdateScreen(timer)

    if (name == 'main_page') and (identify_page(timer, 'options_page', 0)):
        return False
    if (name == 'map_page') and ((intergrative_page_identify(timer) != 1 or PixelChecker(timer, (35, 297), (47, 253, 226)))):
        return False
    if (name == 'build_page') and (intergrative_page_identify(timer) != 1):
        return False
    if (name == 'develop_page') and (intergrative_page_identify(timer) != 3):
        return False

    return any(ImagesExist(timer, template, 0) for template in IdentifyImages[name])


@logit()
def wait_pages(timer: Timer, names, timeout=5, gap=.1):
    start_time = time.time()
    if (isinstance(names, str)):
        names = [names]
    while (True):
        UpdateScreen(timer)
        for i, name in enumerate(names):
            if (identify_page(timer, name, 0)):
                return i + 1

        if (time.time() - start_time > timeout):
            break
        time.sleep(gap)

    raise TimeoutError("identify timeout of" + str(names))


@logit(level=INFO1)
def get_now_page(timer: Timer):
    UpdateScreen(timer)
    for page in ALL_UI:
        if (identify_page(timer, page, need_screen_shot=False, no_log=True)):
            return page
    return None


@logit()
def check_now_page(timer: Timer):
    return identify_page(timer, name=timer.now_page.name, no_log=True)
