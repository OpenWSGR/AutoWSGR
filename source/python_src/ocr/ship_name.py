import easyocr
from utils.api_image import crop_image

from utils.api_image import relative_to_absolute
import time
import cv2

chr_reader = easyocr.Reader(['ch_sim','en'])

def recognize_ship(timer):
    timer.UpdateScreen()
    image = timer.screen
    image = crop_image(image, (0.241, -0.101), (0.444, -0.226))
    cv2.imwrite('tmp.png',image)
    string = chr_reader.readtext(image)
    print(string)