import os
from typing import Protocol

import cv2
import numpy as np

from autowsgr.configs import UserConfig
from autowsgr.constants.data_roots import BIN_ROOT
from autowsgr.timer.backends.api_dll import ApiDll
from autowsgr.utils.io import cv_imread
from autowsgr.utils.logger import Logger


def edit_distance(word1, word2) -> int:
    """
    解题思路，动态规划
        步骤1：将word1与word2前拼接上空格，方便为空时的操作
        步骤2：初始化dp第一个元素，接着初始化dp的第一行与第一列
        步骤3：可通过画表(如: excel里)找到状态转移的规律，填充剩下的dp格子即可
    :return: dp[-1][-1], 返回最后操作的结果
    """
    m, n = len(word1), len(word2)
    if m == 0 and n == 0:
        return 0
    word1, word2 = (
        ' ' + word1,
        ' ' + word2,
    )  # 非常必要的操作，不添加空格话，在Word为空时会比较麻烦
    dp = [[0 for _ in range(n + 1)] for _ in range(m + 1)]
    dp[0][0] = 0  # 初始化dp[0][0] = 0，因为空格对空格不需要任何操作，即0步
    for i in range(1, n + 1):  # 第一行初始化
        dp[0][i] = i
    for i in range(1, m + 1):  # 第一列初始化
        dp[i][0] = i
    for i in range(1, m + 1):  # 逐个填充剩余的dp格子
        for j in range(1, n + 1):
            if word1[i] == word2[j]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1]) + 1
    return dp[-1][-1]


def find_lcseque(s1, s2):
    """求两个字符串的LCS"""
    m = [[0 for x in range(len(s2) + 1)] for y in range(len(s1) + 1)]
    d = [[None for x in range(len(s2) + 1)] for y in range(len(s1) + 1)]
    for p1 in range(len(s1)):
        for p2 in range(len(s2)):
            if s1[p1] == s2[p2]:
                m[p1 + 1][p2 + 1] = m[p1][p2] + 1
                d[p1 + 1][p2 + 1] = 'ok'
            elif m[p1 + 1][p2] > m[p1][p2 + 1]:
                m[p1 + 1][p2 + 1] = m[p1 + 1][p2]
                d[p1 + 1][p2 + 1] = 'left'
            else:
                m[p1 + 1][p2 + 1] = m[p1][p2 + 1]
                d[p1 + 1][p2 + 1] = 'up'
    (p1, p2) = (len(s1), len(s2))
    s = []
    while m[p1][p2]:  # 不为None时
        c = d[p1][p2]
        if c == 'ok':  # 匹配成功，插入该字符，并向左上角找下一个
            s.append(s1[p1 - 1])
            p1 -= 1
            p2 -= 1
        if c == 'left':  # 根据标记，向左找下一个
            p2 -= 1
        if c == 'up':  # 根据标记，向上找下一个
            p1 -= 1
    s.reverse()
    return ''.join(s)


class OCRBackend(Protocol):
    config: UserConfig
    logger: Logger
    WORD_REPLACE: dict[
        str,
        str,
    ]  # 记录中文ocr识别的错误用于替换。主要针对词表缺失的情况，会导致稳定的识别为另一个字
    bin: ApiDll

    def __init_subclass__(cls) -> None:
        cls.bin = ApiDll(os.path.join(BIN_ROOT))

    def read_text(
        self,
        img,
        allowlist: list[str] | None = None,
        sort: str = 'left-to-right',
        **kwargs,
    ):
        """识别文字的具体实现，返回字符串格式识别结果"""
        raise NotImplementedError

    def resize_image_proportionally(self, image, scale_factor):
        """
        等比例扩大图片。

        参数:
        image -- NumPy数组格式的图片
        scale_factor -- 扩大的倍数，例如2表示扩大到原来的两倍

        返回:
        resized_image -- 扩大后的图片
        """
        # 获取原始图片的尺寸
        original_height, original_width = image.shape[:2]

        # 计算新的尺寸
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)

        # 使用cv2.resize函数等比例扩大图片
        return cv2.resize(
            image,
            (new_width, new_height),
            interpolation=cv2.INTER_LINEAR,
        )

    def recognize(
        self,
        img,
        allowlist: list[str] | None = None,
        candidates: list[str] | None = None,
        multiple=False,
        allow_nan=False,
        rgb_select=None,
        tolerance=30,
        scale_factor=2,
        **kwargs,
    ):
        """识别任意字符串, 该函数为最底层封装

        Args:
            scale_factor (int, optional): 图标缩放倍率. Defaults to 2.
        Returns:
            list((int, int), str, float): 中心位置, 字串识别结果, 置信度
        """

        def pre_process_rgb(img, rgb_select=None, tolerance=30):
            # 如果没有提供rgb_select，直接返回原始图像
            if rgb_select is None:
                return img

            # 将BGR图像转换为RGB格式
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            rgb_select_normalized = np.array(rgb_select)
            mask = np.all(np.abs(img_rgb - rgb_select_normalized) <= tolerance, axis=-1)

            # 使用掩码将匹配的像素保留，其他像素设置为255
            result_img = img_rgb.copy()
            result_img[mask] = 0
            result_img[~mask] = 255

            # 将处理后的图像转换回BGR格式
            return cv2.cvtColor(result_img, cv2.COLOR_RGB2BGR)

        def split_image(img: np.ndarray):
            def is_key_line(line: np.ndarray):
                return line.min() != 255
                # for i in range(1, line.shape[0], 8):
                #     if any(val != 255 for val in line[i]):
                #         return True
                # return False

            bias = []
            imgs = []
            last_array = np.ndarray([0, img.shape[1], 3], dtype=np.uint8)
            for i in range(img.shape[0]):
                if (not is_key_line(img[i])) or i == img.shape[0] - 1:
                    if last_array.shape[0] > 8:
                        imgs.append(last_array)
                        bias.append(i - last_array.shape[0])
                    last_array = np.ndarray([0, img.shape[1], 3], dtype=np.uint8)
                    # else:
                else:
                    last_array = np.append(last_array, [img[i]], 0)
            return imgs, bias

        def post_process_text(t):
            for k, v in self.WORD_REPLACE.items():
                t = t.replace(k, v)
            res, name = 'dsjfagiahsdifhaoisd', t
            if candidates is None:
                return name
            for _name in candidates:
                if any((_name.find(char) != -1) for char in name):
                    dis1 = edit_distance(_name, name) / (len(find_lcseque(_name, name)) + 1)
                    dis2 = edit_distance(res, name) / (len(find_lcseque(res, name)) + 1)
                    if dis1 < dis2:
                        res = _name
            return res

        img = pre_process_rgb(img, rgb_select, tolerance)
        if type(img) is str:
            img = cv2.imdecode(
                np.frombuffer(cv_imread(img), np.uint8),
                cv2.IMREAD_COLOR,
            )
        img = self.resize_image_proportionally(img, scale_factor)
        imgs, bias = split_image(img)
        results = []
        for img, bia in zip(imgs, bias, strict=False):
            _results = self.read_text(img, allowlist, **kwargs)
            _results = [x for x in _results if x[1] != '']  # 去除空匹配
            _results = [(t[0], post_process_text(t[1]), t[2]) for t in _results]
            for result in _results:
                results.append(  # noqa: PERF401
                    (
                        [
                            (result[0][0]) // scale_factor,
                            (result[0][1] + bia) // scale_factor,
                        ],
                        result[1],
                        result[2],
                    ),
                )
        if self.config.show_ocr_info:
            self.logger.debug(f'修正OCR结果：{results}')

        if allow_nan and not results:
            return None

        if multiple:
            return results
        if not results:
            results = ['Unknown']
        return results[0]

    def recognize_number(
        self,
        img,
        extra_chars='',
        multiple=False,
        allow_nan=False,
        **kwargs,
    ):
        """识别数字"""

        def process_number(t: str):
            # 今日胖次、掉落; 决战升级经验等
            if '/' in t:
                nums = t.split('/')
                assert len(nums) == 2
                return process_number(nums[0]), process_number(nums[1])

            # 决战，费用是f"x{cost}"格式
            t = t.lstrip('xXKk')
            # 战后经验值 f"Lv.{exp}"格式
            t = t.lstrip('Lv.')
            # 建造资源有前导0
            if t != '0':
                t = t.lstrip('0')

            # 资源可以是K/M结尾
            if t.endswith(('K', 'k')):
                return eval(t[:-1]) * 1000
            if t.endswith('M'):
                return eval(t[:-1]) * 1000000

            return eval(t)

        results = self.recognize(
            img,
            allowlist='0123456789' + extra_chars,
            multiple=True,
            **kwargs,
        )
        results = [(t[0], process_number(t[1]), t[2]) for t in results]
        if self.config.show_ocr_info:
            self.logger.debug(f'数字解析结果：{results}')

        if allow_nan and not results:
            return None

        if multiple:
            return results
        if len(results) != 1:
            self.logger.warning(f'OCR识别数字失败: {results}')
            results = []
        return results[0]

    def recognize_ship(self, image, candidates, **kwargs):
        """传入一张图片,返回舰船信息,包括名字和舰船型号"""
        if isinstance(image, str):
            image_path = os.path.abspath(image)
            img = cv2.imread(image_path)
        else:
            img = image
        location = self.bin.locate(img)
        ret = []
        for i in range(len(location)):
            res = self.recognize(
                img[location[i][0] - 1 : location[i][1] + 1],
                multiple=True,
                candidates=candidates,
                **kwargs,
            )
            for j in range(len(res)):
                res[j][0][1] = res[j][0][1] + location[i][0] - 1
            ret += res

        return ret

    # def recognize_time(self, img, format="%H:%M:%S"):
    #     """识别时间"""
    #     text = self.recognize(img, allowlist="0123456789:").replace(" ", "")
    #     return str2time(text, format)


class EasyocrBackend(OCRBackend):
    def __init__(self, config: UserConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self.WORD_REPLACE = {
            '鲍鱼': '鲃鱼',
            '鲴鱼': '鲃鱼',
        }
        import easyocr

        self.reader = easyocr.Reader(['ch_sim', 'en'])

    def read_text(
        self,
        img,
        allowlist: list[str] | None = None,
        sort='left-to-right',
        # TODO：以下参数可能需要调整，以获得最好OCR性能
        min_size=7,
        text_threshold=0.25,
        low_text=0.3,
        **kwargs,
    ):
        """识别文字的具体实现，返回字符串格式识别结果"""

        def get_center(pos1, pos2):
            x1, y1 = pos1
            x2, y2 = pos2
            return (x1 + x2) / 2, (y1 + y2) / 2

        results = self.reader.readtext(
            img,
            allowlist=allowlist,
            min_size=min_size,
            text_threshold=text_threshold,
            low_text=low_text,
            **kwargs,
        )
        results = [(get_center(r[0][0], r[0][2]), r[1], r[2]) for r in results]

        if sort == 'left-to-right':
            results = sorted(results, key=lambda x: x[0][0])
        elif sort == 'top-to-bottom':
            results = sorted(results, key=lambda x: x[0][1])
        else:
            raise ValueError(f'Invalid sort method: {sort}')

        if self.config.show_ocr_info:
            self.logger.debug(f'原始OCR结果: {results}')
        return results


class PaddleOCRBackend(OCRBackend):

    def __init__(self, config: UserConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self.WORD_REPLACE = {
            '鲍鱼': '鲃鱼',
        }

        # TODO:后期单独训练模型，提高识别准确率，暂时使用现成的模型
        from paddleocr import PaddleOCR

        self.reader = PaddleOCR(
            use_angle_cls=True,
            use_gpu=True,
            show_log=False,
            lang='ch',
        )  # need to run only once to download and load model into memory

    def read_text(self, img, allowlist, **kwargs):

        def get_center(pos1, pos2):
            x1, y1 = pos1
            x2, y2 = pos2
            return (x1 + x2) / 2, (y1 + y2) / 2

        results = self.reader.ocr(img, cls=False, **kwargs)
        results = [] if results == [None] else results[0]
        results = [(get_center(r[0][1], r[0][3]), r[1][0], r[1][1]) for r in results]
        if self.config.show_ocr_info:
            self.logger.debug(f'原始OCR结果: {results}')
        return results
