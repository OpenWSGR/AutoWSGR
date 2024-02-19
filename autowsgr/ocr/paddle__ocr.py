from paddleocr import PaddleOCR, draw_ocr
from AutoWSGR.utils.api_image import crop_image


en_paddle_ocr = None
cn_paddle_ocr = None

def load_en_ocr():
    global en_paddle_ocr
    en_paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en",show_log = False)  # need to run only once to download and load model into memory


def load_ch_ocr():
    global cn_paddle_ocr
    cn_paddle_ocr = PaddleOCR(use_angle_cls=True, lang="ch",show_log = False)  # need to run only once to download and load model into memory

def paddle_ocr(image, language = "en"):

    if language == "ch":
        if cn_paddle_ocr == None:
            load_ch_ocr()
        result = cn_paddle_ocr.ocr(image , cls=True)
    elif language == "en" :
        if en_paddle_ocr == None:
            load_en_ocr()
        result = en_paddle_ocr.ocr(image,cls=True)
    #print(f"原始数据为： {result}")
    try:
        return result[0]
    except:
        result = None
    return result 

"""if __name__ == "__main__":
    image="4.PNG"
    #image_crop = crop_image(image, resolution=timer.config.resolution)
    result = paddle_ocr(image,language = "ch")
    print(result)"""


