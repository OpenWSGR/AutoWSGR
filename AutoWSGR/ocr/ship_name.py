# import easyocr
import time

import cv2
from AutoWSGR.utils.api_image import crop_image, relative_to_absolute

# chr_reader = easyocr.Reader(['ch_sim','en'])

# def recognize_ship(timer):
#     timer.update_screen()
#     image = timer.screen
#     image = crop_image(image, (0.241, -0.101), (0.444, -0.226))
#     cv2.imwrite('tmp.png',image)
#     string = chr_reader.readtext(image)
#     print(string)
