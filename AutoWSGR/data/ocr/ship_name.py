# import easyocr
import os
import sys

sys.path.append(os.getcwd())
# sys.path.append(os.getcwd() + r"\source\python_src")

import easyocr
import numpy as np
from controller.run_timer import Timer
from utils.api_image import crop_image, relative_to_absolute
from utils.io import yaml_to_dict

ch_reader = easyocr.Reader(['ch_sim'], gpu=False)
en_reader = easyocr.Reader(['en'], gpu=False)
_names = yaml_to_dict('data/ocr/ship_name.yaml').values()
names = []
for name in _names:
    names += name
# chr_reader = easyocr.Reader(['ch_sim','en'])

def find_lcseque(s1, s2): 
    """求两个字符串的LCS
    """
    m = [ [ 0 for x in range(len(s2)+1) ] for y in range(len(s1)+1) ] 
    d = [ [ None for x in range(len(s2)+1) ] for y in range(len(s1)+1) ] 
    for p1 in range(len(s1)): 
        for p2 in range(len(s2)): 
            if s1[p1] == s2[p2]:            
                m[p1+1][p2+1] = m[p1][p2]+1
                d[p1+1][p2+1] = 'ok'          
            elif m[p1+1][p2] > m[p1][p2+1]:  
                m[p1+1][p2+1] = m[p1+1][p2] 
                d[p1+1][p2+1] = 'left'          
            else:                           
                m[p1+1][p2+1] = m[p1][p2+1]   
                d[p1+1][p2+1] = 'up'         
 
    (p1, p2) = (len(s1), len(s2)) 
    s = [] 
    while m[p1][p2]:    # 不为None时
        c = d[p1][p2]
        if c == 'ok':   # 匹配成功，插入该字符，并向左上角找下一个
            s.append(s1[p1-1])
            p1 -= 1
            p2 -= 1 
        if c =='left':  # 根据标记，向左找下一个
            p2 -= 1
        if c == 'up':   # 根据标记，向上找下一个
            p1 -= 1
    s.reverse() 
    return ''.join(s) 


def get_allow(names):
    char_set = set()
    for name in names:
        for char in name:
            char_set.add(char)
    res = ""
    for char in char_set:
        res += char
    return res


def recognize_ship(image, names, char_list=None):
    if(char_list is None):
        char_list = get_allow(names)
    print(char_list)
    result = ch_reader.readtext(image, allowlist=char_list)
    for box in result:
        res, lcs, name = "", "", box[1]
        for _name in names:
            if(any([(_name.find(char) != -1) for char in name])):
                lcs_str = find_lcseque(_name, name)
                if(len(lcs_str) > len(lcs) or (len(lcs_str) == len(lcs) and abs(len(name) - len(res)) > abs(len(name) - len(_name)))):
                    res, lcs = _name, lcs_str
        print(res)
        print(box)

def recognize_ship_bathroom(timer:Timer):
    pass


def recover(image):
    for p in image:
        pass
    

if __name__ == '__main__':
    recognize_ship(r'source\c_src\1.PNG', names, "博格兰利百眼巨人祥凤瑞凤甘比尔湾塞班桑提圣哈辛托瓜达卡纳尔神鹰竞技神独角兽鹞")
