import sys

if sys.platform == "darwin":
    import cnocr

from autowsgr.constants.other_constants import CN_TYPE_TO_EN_TYPE


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
    def enemy(self,img):
        model = "ch_ppocr_mobile_v2.0"

        typeText = self.ocr[model].ocr(img)
        if len(typeText) > 0:
            return CN_TYPE_TO_EN_TYPE.get(typeText[0]["text"])
        else:
            return "NO"

def filterF(result):
    if result["score"] <= 0.5:
        return False
    if result["text"] == "I":
        return True
    if result["text"] == "J":
        return True
    return result["score"] > 0.83 and result["text"] != ""