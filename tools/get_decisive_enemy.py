import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from AutoWSGR.ocr.ship_name import recognize, get_allow
from AutoWSGR.constants.other_constants import ALL_SHIP_TYPES_CN

DEBUG = False

def split_str(str, keywords):
    res = []
    while(len(str)):
        flag = 0
        for word in keywords:
            if word == str[:len(word)]:
                res.append(word)
                str = str[len(word):]
                flag = 1
        if(flag == 0):
            str = str[1:]
    return res
    
def recognize_decisive_enemy(image):
    allow = get_allow(ALL_SHIP_TYPES_CN)
    char = 'A'
    for box in recognize(image, char_list=allow + '/'):
        try:
            text = box[1]
            if(DEBUG):
                print(text)
            assert(isinstance(text, str))
            enemy = split_str(text, keywords=ALL_SHIP_TYPES_CN)
            print(char,":", [""] + enemy)
        except Exception as e:
            print(e)
            print(char)
        char = chr(ord(char) + 1)    
            
if __name__ == '__main__':
    recognize_decisive_enemy(r'AutoWSGR\data\map\decisive_battle\3-6-1.PNG')