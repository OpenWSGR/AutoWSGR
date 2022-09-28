import os, sys

sys.path.append(os.path.dirname(os.path.dirname(__file__))) 

from wsgr import start_script
import easyocr 
import keyboard

def recognize_image(event:keyboard.KeyboardEvent):
    if(event.event_type != 'down' or event.name != 'P'):
        return 
    timer.update_screen()
    result = en_reader.readtext(timer.screen, allowlist=["ABCDEFGHIJKLMNOPQRST"])
    for box in result:
        print(box)

en_reader = easyocr.Reader(['en'])
timer = start_script()
print("HOOKED")
keyboard.hook()


