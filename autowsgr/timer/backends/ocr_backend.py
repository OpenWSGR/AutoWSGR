import os
import subprocess
from typing import List, Tuple

import cv2
import numpy as np
from thefuzz import process

from autowsgr.constants.data_roots import TUNNEL_ROOT


class OCRBackend:
    WORD_REPLACE = None  # 记录中文ocr识别的错误用于替换。主要针对词表缺失的情况，会导致稳定的识别为另一个字

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def read_text(
        self, img, allowlist: List[str] = None, sort: str = "left-to-right", **kwargs
    ):
        """识别文字的具体实现，返回字符串格式识别结果"""
        raise NotImplementedError

    def recognize(
        self,
        img,
        allowlist: List[str] = None,
        candidates: List[str] = None,
        multiple=False,
        allow_nan=False,
        rgb_select=None,
        tolerance=30,
        **kwargs,
    ):
        """识别任意字符串"""

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
            result_img_bgr = cv2.cvtColor(result_img, cv2.COLOR_RGB2BGR)

            return result_img_bgr

        def post_process_text(t):
            for k, v in self.WORD_REPLACE.items():
                t = t.replace(k, v)
            if candidates:
                t = process.extractOne(t, candidates)[0]
            return t

        img = pre_process_rgb(img, rgb_select, tolerance)
        results = self.read_text(img, allowlist, **kwargs)
        results = [(t[0], post_process_text(t[1]), t[2]) for t in results]
        if self.config.SHOW_OCR_INFO:
            self.logger.debug(f"修正OCR结果：{results}")

        if allow_nan and not results:
            return None

        if multiple:
            return results
        else:
            if not results:
                print(f"OCR识别失败: {results}")
                results = ["Unkown"]
            return results[0]

    def recognize_number(
        self, img, extra_chars="", multiple=False, allow_nan=False, **kwargs
    ):
        """识别数字"""

        def process_number(t: str):
            # 今日胖次、掉落; 决战升级经验等
            if "/" in t:
                nums = t.split("/")
                assert len(nums) == 2
                return process_number(nums[0]), process_number(nums[1])

            # 决战，费用是f"x{cost}"格式
            t = t.lstrip("xX")
            # 战后经验值 f"Lv.{exp}"格式
            t = t.lstrip("Lv.")
            # 建造资源有前导0
            if t != "0":
                t = t.lstrip("0")

            # 资源可以是K/M结尾
            if t.endswith("K") or t.endswith("k"):
                return eval(t[:-1]) * 1000
            if t.endswith("M"):
                return eval(t[:-1]) * 1000000

            return eval(t)

        results = self.recognize(
            img, allowlist="0123456789" + extra_chars, multiple=True, **kwargs
        )
        results = [(t[0], process_number(t[1]), t[2]) for t in results]
        if self.config.SHOW_OCR_INFO:
            self.logger.debug(f"数字解析结果：{results}")

        if allow_nan and not results:
            return None

        if multiple:
            return results
        else:
            if not len(results) == 1:
                self.logger.error(f"OCR识别数字失败: {results}")
                results = []
            return results[0]

    def recognize_ship(self, image, candidates, **kwargs):
        """传入一张图片,返回舰船信息,包括名字和舰船型号"""
        if isinstance(image, str):
            image_path = os.path.abspath(image)
        else:
            image_path = os.path.join(TUNNEL_ROOT, "OCR.PNG")
            cv2.imwrite(image_path, image)
        with open(os.path.join(TUNNEL_ROOT, "locator.in"), "w+") as f:
            f.write(image_path)
        locator_exe = os.path.join(TUNNEL_ROOT, "locator.exe")
        subprocess.run([locator_exe, TUNNEL_ROOT])
        if os.path.exists(os.path.join(TUNNEL_ROOT, "1.PNG")):
            img_path = os.path.join(TUNNEL_ROOT, "1.PNG")
        else:
            img_path = "1.PNG"
        return self.recognize(img_path, candidates=candidates, multiple=True, **kwargs)

    # def recognize_time(self, img, format="%H:%M:%S"):
    #     """识别时间"""
    #     text = self.recognize(img, allowlist="0123456789:").replace(" ", "")
    #     return str2time(text, format)


class EasyocrBackend(OCRBackend):
    WORD_REPLACE = {
        "鲍鱼": "鲃鱼",
        "鲴鱼": "鲃鱼",
    }

    def __init__(self, config, logger) -> None:
        super().__init__(config, logger)
        import easyocr

        self.reader = easyocr.Reader(["ch_sim", "en"])

    def read_text(
        self,
        img,
        allowlist: List[str] = None,
        sort="left-to-right",
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

        if sort == "left-to-right":
            results = sorted(results, key=lambda x: x[0][0])
        elif sort == "top-to-bottom":
            results = sorted(results, key=lambda x: x[0][1])
        else:
            raise ValueError(f"Invalid sort method: {sort}")

        if self.config.SHOW_OCR_INFO:
            self.logger.debug(f"原始OCR结果: {results}")
        return results


class PaddleOCRBackend(OCRBackend):
    WORD_REPLACE = {
        "鲍鱼": "鲃鱼",
    }

    def __init__(self, config, logger) -> None:
        super().__init__(config, logger)
        # TODO:后期单独训练模型，提高识别准确率，暂时使用现成的模型
        from paddleocr import PaddleOCR

        self.reader = PaddleOCR(
            use_angle_cls=True,
            det_model_dir="https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar",
            rec_model_dir="https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_server_infer.tar",
            show_log=False,
            lang="ch",
        )  # need to run only once to download and load model into memory

    def read_text(self, img, allowlist, **kwargs):

        def get_center(pos1, pos2):
            x1, y1 = pos1
            x2, y2 = pos2
            return (x1 + x2) / 2, (y1 + y2) / 2

        results = self.reader.ocr(img, cls=False, **kwargs)
        self.logger.log_image(img, name=None, ignore_existed_image=True)
        if results == [None]:
            results = []
        else:
            results = results[0]
        results = [(get_center(r[0][1], r[0][3]), r[1][0], r[1][1]) for r in results]
        if self.config.SHOW_OCR_INFO:
            self.logger.debug(f"原始OCR结果: {results}")
        return results
