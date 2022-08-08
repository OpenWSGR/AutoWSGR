
from typing import Tuple
from api.api_android import *
from supports import *
from airtest.core.cv import *

__all__ = ["MyTemplate", "GetImagePosition", "ImagesExist", "WaitImage", "ClickImage",
           "WaitImages", "UpdateScreen", "PixelChecker"]


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


class PixelChecker():
    def __init__(self, timer: Timer, position, bgr_color, distance=30):
        self.timer = timer
        self.position = timer.covert_position(*position)
        self.color = bgr_color
        self.distance = distance

    def __bool__(self):
        color = self.timer.screen[self.position[1]][self.position[0]]
        return bool(CalcDis(color, self.color) < self.distance ** 2)


def locateCenterOnImage(timer: Timer, image: np.ndarray, query: MyTemplate, confidence=0.85, this_mehods=['tpl']):
    """从原图像中尝试找出一个置信度相对于模板图像最高的矩阵区域的中心坐标

    Args:
        timer (Timer): 数据记录器
        image (np.ndarray): 原图像
        query (MyTemplate): 模板图像
        confidence (float, optional): 置信度阈值. Defaults to 0.85.
        this_mehods (list, optional): 匹配方式. Defaults to ['tpl'].

    Returns:
        如果匹配结果中有超过阈值的,返回置信度最高的结果的中心绝对坐标:Tuple(int,int)

        否则返回 None 
    """
    query.threshold = confidence
    if match_pos := query.match_in(image, this_methods=this_mehods):
        return match_pos
    else:
        return None


def locateCenterOnScreen(timer: Timer, query: MyTemplate, confidence=0.85, this_mehods=["tpl"]):
    """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
        参考 locateCenterOnImage
    Returns:
        如果找到返回一个二元组表示绝对坐标

        否则返回 None
    """
    return locateCenterOnImage(timer, timer.screen, query, confidence, this_mehods)


@logit()
def GetImagePosition(timer: Timer, image: MyTemplate, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
    """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
        参考 locateCenterOnScreen
    Args:
        need_screen_shot (int, optional): 是否重新截取屏幕. Defaults to 1.
    Returns:
        如果找到:返回一个二元组表示相对坐标 (相对 960x540 屏幕)

        否则返回 None
    """
    if(need_screen_shot == 1):
        UpdateScreen(timer)
    res = locateCenterOnScreen(timer, image, confidence, this_methods)
    if res is None:
        return None
    return timer.covert_position(res[0], res[1], mode='this_to_960')


@logit()
def ImagesExist(timer: Timer, images, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
    """判断图像是否存在于屏幕中
    Returns:
        bool:如果存在为 True 否则为 False 
    """
    if not isinstance(images, list):
        images = [images]
    if need_screen_shot:
        UpdateScreen(timer)
    return any(GetImagePosition(timer, image, 0, confidence, this_methods, no_log=True) is not None for image in images)


@logit()
def WaitImage(timer: Timer, image: MyTemplate, confidence=0.85, timeout=10, gap=.15, after_get_delay=0, this_methods=["tpl"]):
    """等待一张图片出现在屏幕中,置信度超过一定阈值

    Args:
        timeout (int, optional): 最大等待时间. Defaults to 10.
    Returns:
        如果在 timeout 秒内发现,返回一个二元组表示其相对(960x540 屏幕)位置

        否则返回 False
    """
    if(timeout < 0):
        raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))
    StartTime = time.time()
    while(True):
        x = GetImagePosition(timer, image, 1, confidence, this_methods, no_log=True)
        if(x != None):
            time.sleep(after_get_delay)
            return x
        if(time.time()-StartTime > timeout):
            time.sleep(gap)
            return False
        time.sleep(gap)


@logit(level=INFO1)
def ClickImage(timer: Timer, image: MyTemplate, must_click=False, timeout=0, delay=0.5):
    """点击一张图片的中心位置
    Args:
        image (MyTemplate): 目标图片
        must_click (bool, optional): 如果为 True,点击失败则抛出异常. Defaults to False.
        timeout (int, optional): 等待延时. Defaults to 0.
        delay (float, optional): 点击后延时. Defaults to 0.5.

    Raises:
        NotFoundErr: 如果在 timeout 时间内未找到则抛出该异常
    """
    if(timeout < 0):
        raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))
    if(delay < 0):
        raise ValueError("arg 'delay' should at least be 0 but is ", str(delay))
    pos = WaitImage(timer, image, timeout=timeout)
    if(pos == False):
        if(must_click == False):
            return False
        else:
            raise ImageNotFoundErr("Target image not found:" + str(image.filepath))

    click(timer, pos[0], pos[1], delay=delay)
    return True


@logit()
def WaitImages(timer: Timer, images=[], confidence=0.85, gap=.15, after_get_delay=0, timeout=10, *args, **kwargs):
    """等待一系列图片中的一个在屏幕中出现

    Args:
        images (list, optional): 很多图片,可以是列表或字典. Defaults to [].
        confidence (_type_, optional): 置信度. Defaults to 0.85.
        timeout (int, optional): 最长等待时间. Defaults to 10.

    Raises:
        TypeError: image_list 中有不合法参数

    Returns:
        None: 未找到任何图片
        a number of int: 第一个出现的图片的下标(0-based) if images is a list
        the key of the value if images is a dict
    """
    images = copy.copy(images)
    if(isinstance(images, MyTemplate)):
        images = [images]
    if(isinstance(images, list) or isinstance(images, Tuple)):
        for i in range(len(images)):
            images[i] = (i, images[i])
    if(isinstance(images, dict)):
        images = images.items()

    if(timeout < 0):
        raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))

    StartTime = time.time()
    while(True):
        UpdateScreen(timer, no_log=True)
        for res, image in images:
            if(ImagesExist(timer, image, 0, confidence, no_log=True)):
                time.sleep(after_get_delay)
                return res
        time.sleep(gap)
        if(time.time() - StartTime > timeout):
            return None
