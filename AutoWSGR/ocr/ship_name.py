# import easyocr
import os
import functools
import threading
import easyocr
import cv2

from AutoWSGR.constants.data_roots import TUNNEL_ROOT
from AutoWSGR.constants.settings import S
from AutoWSGR.utils.debug import print_debug
from AutoWSGR.utils.operator import unzip_element

en_reader = None
ch_reader = None

def load_en_reader():
    global en_reader
    print_debug(S.SHOW_OCR_INFO, "start loading en_reader")
    en_reader = easyocr.Reader(['en'], gpu=True)
    print_debug(S.SHOW_OCR_INFO, "end loading en_reader")


def load_ch_reader():
    global ch_reader
    print_debug(S.SHOW_OCR_INFO, "start loading ch_reader")
    ch_reader = easyocr.Reader(['ch_sim'], gpu=True)
    print_debug(S.SHOW_OCR_INFO, "end loading ch_reader")


def edit_distance(word1, word2) -> int:
        '''
        解题思路，动态规划
            步骤1：将word1与word2前拼接上空格，方便为空时的操作
            步骤2：初始化dp第一个元素，接着初始化dp的第一行与第一列
            步骤3：可通过画表(如: excel里)找到状态转移的规律，填充剩下的dp格子即可
        :return: dp[-1][-1], 返回最后操作的结果
        '''
        m, n = len(word1), len(word2)
        if m == 0 and n == 0: return 0
        word1, word2 = ' '+ word1, ' '+ word2                   # 非常必要的操作，不添加空格话，在Word为空时会比较麻烦
        dp = [[0 for _ in range(n+1)] for _ in range(m+1)]
        dp[0][0] = 0                                            # 初始化dp[0][0] = 0，因为空格对空格不需要任何操作，即0步
        for i in range(1, n+1):                                 # 第一行初始化
            dp[0][i] = i
        for i in range(1, m+1):                                 # 第一列初始化
            dp[i][0] = i                                            
        for i in range(1, m+1):                                 # 逐个填充剩余的dp格子                      
            for j in range(1, n+1):
                if word1[i] == word2[j]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = min(dp[i-1][j-1], dp[i-1][j], dp[i][j-1]) + 1
        return dp[-1][-1]


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
    for name in unzip_element(names):
        for char in name:
            char_set.add(char)
    res = ""
    for char in char_set:
        res += char
    return res


def compare_box(A, B):
    """对 easyocr.readtext 返回的 box 进行排序
    """
    k1, k2 = A[0][0], B[0][0]
    if(abs(k1[0] - k2[0]) <= 5 and abs(k1[1] - k2[1]) <= 5):return 0
    if(abs(k1[1] - k2[1]) > 5):
        if(k1[1] < k2[1]):return -1
        else: return 1
    else:
        if(k1[0] < k2[1]):return -1
        else: return 1


def recognize(image, char_lsit, min_size=7, text_threshold=.55, low_text=.3):
    return ch_reader.readtext(image, allowlist=char_lsit, min_size=min_size, text_threshold=text_threshold, low_text=low_text)


def recognize_number(image, ex_list="", min_size=7, text_threshold=.55, low_text=.3):
    """识别数字和 ex_list 的字符, 返回识别结果列表,
    Returns:
        list(result): 一个 result 为 [position, text, confidence]
    """
    char_list = "0123456789"
    for ch in ex_list:
        if(char_list.find(ch) == -1):
            char_list += ch
    return en_reader.readtext(image, allowlist=char_list, min_size=min_size, text_threshold=text_threshold, low_text=low_text)
    

def _recognize_ship(image, names, char_list=None, min_size=7, text_threshold=.55, low_text=.3):
    """识别没有预处理过的图片中的舰船, 返回识别结果列表,
    Returns:
        list(result): 一个 result 为 [ship_name, left_top]
    """
    if(char_list is None):
        char_list = get_allow(names)
    result = ch_reader.readtext(image, allowlist=char_list, min_size=min_size, text_threshold=text_threshold, low_text=low_text)
    results = []
    # cv2.imshow("PIC", cv2.imread(image))
    # cv2.waitKey(2)
    sorted(result, key=functools.cmp_to_key(compare_box))
    for box in result:
        res, lcs, name = "", "", box[1]
        for _name in names:
            if(any([(_name.find(char) != -1) for char in name])):
                dis1 = edit_distance(_name, name)
                dis2 = edit_distance(res, name)
                if(dis1 < dis2):
                    res = _name    
        results.append((res, box[0]))
    print_debug(S.SHOW_OCR_INFO, result)
    print_debug(S.SHOW_OCR_INFO, results)
    if(len(results) == 0):
        results.append(("Unknown", (0, 0)))
    return results


def recognize_ship(image, names, char_list=None, min_size=7, text_threshold=.55, low_text=.3):
    """传入一张图片,返回舰船信息,包括名字和舰船型号

    Args:
        image (_type_): _description_
        names (_type_): _description_
        char_list (_type_, optional): _description_. Defaults to None.
    """
    if(isinstance(image, str)):
        image_path = os.path.abspath(image)
    else:
        image_path = os.path.join(TUNNEL_ROOT, "OCR.PNG")
        cv2.imwrite(image_path, image)
    if(char_list is None):
        char_list = get_allow(names)
    with open(os.path.join(TUNNEL_ROOT, "locator.in"), 'w+') as f:
        f.write(image_path)
    os.system(f"{os.path.join(TUNNEL_ROOT, 'locator.exe')} {TUNNEL_ROOT}")
    if (os.path.exists(os.path.join(TUNNEL_ROOT, '1.PNG'))):
        result = _recognize_ship(os.path.join(TUNNEL_ROOT, '1.PNG'), names, char_list, min_size=min_size, text_threshold=text_threshold, low_text=low_text)
    else:
        result = _recognize_ship('1.PNG', names, char_list, min_size=min_size, text_threshold=text_threshold, low_text=low_text)
    return result


def recover(image):
    for p in image:
        pass

p1 = threading.Thread(target=load_ch_reader)
p2 = threading.Thread(target=load_en_reader)
p1.start()
p2.start()
p1.join()
p2.join()


if __name__ == '__main__':
    # print(os.path.abspath(r'data\images\ocr_test\2.PNG'))
    # print(recognize_ship(r'data\images\ocr_test\4.PNG', ship_names))
    # print(_recognize_ship(r'data\images\ocr_test\5.PNG', ship_names))
    print(recognize_number(r'data\images\ocr_test\7.PNG', "x"))
    print(recognize_number(r'data\images\ocr_test\8.PNG', "x"))
    print(recognize_number(r'data\images\ocr_test\9.PNG', "x"))
    print(recognize_number(r'data\images\ocr_test\10.PNG', "Lv.(/)"))
