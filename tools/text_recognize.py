from time import time

import cv2

from autowsgr.ocr.ship_name import recognize
from autowsgr.scripts.main import start_script
from autowsgr.utils.api_image import absolute_to_relative

last_point = None


def on_mouse(event, x, y, flags, param):
    global last_point
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    print(absolute_to_relative((x, y), resolution=(1280, 720)))
    print(x, y)
    if last_point == None:
        # if True:
        last_point = (x, y)
        return

    image = screen[last_point[1] : y, last_point[0] : x]
    timer.logger.log_image(image, f"{time()}.PNG")
    result = recognize(image)
    print(result)
    last_point = None


timer = start_script("tests/user_settings.yaml")
while True:
    cv2.waitKey(0)
    screen = timer.get_screen()
    window_name = "window"
    cv2.namedWindow(window_name)
    cv2.imshow(window_name, screen)
    cv2.setMouseCallback(window_name, on_mouse)
