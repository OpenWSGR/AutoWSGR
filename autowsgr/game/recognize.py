# 识别后端为go实现，传入扫描后的像素数组，返回舰船简称的数组
# 脚本timer启动后运行这里的代码，此包会启动go服务，然后每一秒发送给go心跳，go三秒内没有接收心跳会自动关闭
# 本包连续三次心跳失败会重新启动go服务
import os
import subprocess
import sys
import threading
import numpy as np
import json

import requests
from PIL.Image import Image

from autowsgr.constants.data_roots import TUNNEL_ROOT
from autowsgr.constants.positions import TYPE_SCAN_AREA
from autowsgr.game.my_cnocr import MyCnOcr
from autowsgr.utils.io import delete_file, read_file
from autowsgr.utils.math_functions import matrix_to_str

def __get_insteps(timer, img: Image, type='exercise'):
    plat = sys.platform
    platFun = {
        'win32': lambda: get_enemy_condition_win(img, type),
        'linux': 'linux',
        'darwin': lambda: get_enemy_condition_mac(timer, img, type),
    }
    return platFun[plat]()


def enemy_condition(timer, img: Image, type='exercise'):
    return __get_insteps(timer, img, type)

def get_enemy_condition_win(img: Image, type='exercise'):
    """获取敌方舰船类型数据并返回一个字典, 具体图像识别为黑箱, 采用 C++ 实现"""

    # 处理图像并将参数传递给识别图像的程序
    input_path = os.path.join(TUNNEL_ROOT, 'args.in')
    output_path = os.path.join(TUNNEL_ROOT, 'res.out')
    delete_file(output_path)
    args = 'recognize\n6\n'
    for area in TYPE_SCAN_AREA[type]:
        arr = np.array(img.crop(area))
        args += matrix_to_str(arr)
    with open(input_path, 'w') as f:
        f.write(args)
    recognize_enemy_exe = os.path.join(TUNNEL_ROOT, 'recognize_enemy.exe')
    result = subprocess.run([recognize_enemy_exe], cwd=TUNNEL_ROOT)
    print(f'Return code: {result.returncode}')
    print(f'Standard output: {result.stdout}')
    print(f'Standard error: {result.stderr}')
    # 获取并解析结果
    return read_file(os.path.join(TUNNEL_ROOT, 'res.out')).split()

def get_enemy_condition_mac(timer, img: Image, type='exercise'):
    result = []
    ocr = MyCnOcr()
    for area in TYPE_SCAN_AREA[type]:
        arr = np.array(img.crop(area))
        res = ocr.enemy(arr)
        result.append(res)

    return result
