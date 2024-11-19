from airtest.core.api import connect_device
import cnocr
import numpy as np
from PIL import Image

from autowsgr.constants.other_constants import CN_TYPE_TO_EN_TYPE
from autowsgr.constants.positions import TYPE_SCAN_AREA

class MyCnOcr:
    def __init__(self):
        self.ocr = {
            "en_PP-OCRv3" :cnocr.CnOcr(rec_root=".",
                          model_backend='onnx',
                          det_model_name="naive_det",
                          rec_model_name="en_PP-OCRv3",
                          cand_alphabet='ABCDEFGHIJ'),
            "scene-densenet_lite_136-gru":cnocr.CnOcr(rec_root=".",
                          model_backend='onnx',
                          det_model_name="naive_det",
                          rec_model_name="scene-densenet_lite_136-gru",
                          cand_alphabet='ABCDEFGHIJ'),
            "ch_ppocr_mobile_v2.0":cnocr.CnOcr(rec_root=".",
                          model_backend='onnx',
                          det_model_name="naive_det",
                          rec_model_name="ch_ppocr_mobile_v2.0"),

        }

        return

    def myMap(self, npImg):
        models = [
            "scene-densenet_lite_136-gru",
            "en_PP-OCRv3",
        ]
        res = []
        for model in models:
            ss = self.ocr[model].ocr(npImg)
            re = list(filter(filterF, ss))
            res.extend(re)

        if len(res) > 0:
            return res[0]["text"]
        else:
            return ""
    def enemy(self,img:Image):
        model = "ch_ppocr_mobile_v2.0"


        req = []
        for area in TYPE_SCAN_AREA[1]:
            arr = np.array(img.crop(area))

            res = self.ocr[model].ocr(arr)
            req.append(res)
            print(res)
        return req

def filterF(result):
    if result["score"] <= 0.5:
        return False
    if result["text"] == "I":
        return True
    if result["text"] == "J":
        return True
    return result["score"] > 0.83 and result["text"] != ""

if __name__ == '__main__':
    mycn = MyCnOcr()

    for k, p in enumerate(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]):
    # for k, p in enumerate(["B"]):
        res = mycn.myMap(f'./node/{p}.PNG')
        print(res)

    # mycn.d("")
    # s = "127.0.0.1:16416"
    # android = f'Android:///{s}'
    # dev = connect_device(android)
    # img = dev.snapshot(quality=99)
    # imgs = Image.fromarray(img).convert('L')
    # imgs = imgs.resize((960, 540))
    # mycn = MyCnOcr()
    # print(mycn.e(imgs))