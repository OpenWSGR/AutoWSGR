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

def start_go():
    recognize_enemy_exe = os.path.join(TUNNEL_ROOT, 'main')
    result = subprocess.Popen([recognize_enemy_exe], cwd=TUNNEL_ROOT, text=True, shell=True)
    print(f'Return code: {result.returncode}')
    print(f'Standard output: {result.stdout}')
    print(f'Standard error: {result.stderr}')
    ping()


def ping():
    response = requests.get('http://0.0.0.0:8080/ping', timeout=5)
    if response.status_code == 200:
        print('go服务正常')
    else:
        start_go()

    threading.Timer(3, ping).start()


def repeat_task(interval, function, *args, **kwargs):
    """
    重复执行任务的函数。

    :param interval: 任务之间的间隔时间（秒）
    :param function: 要执行的函数
    :param args: 传递给函数的位置参数
    :param kwargs: 传递给函数的关键字参数
    """

    def wrapper():
        try:
            function(*args, **kwargs)
        except Exception as e:
            print(f'An error occurred: {e}')
        finally:
            # 重新设置定时器
            threading.Timer(interval, wrapper).start()

    # 第一次启动定时器
    threading.Timer(interval, wrapper).start()


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
    global go_port

    req = []
    for area in TYPE_SCAN_AREA[type]:
        arr = np.array(img.crop(area))

        groupPoints = []
        for points in arr.tolist():
            groupPoints.extend(points)

        req.append(groupPoints)

    headers = {
        'Content-Type': 'application/json',
    }
    data = json.dumps(req)

    result = ''
    response = requests.post('http://0.0.0.0:8080/enemy', data=data, headers=headers, timeout=5)
    if response.status_code == 200:
        resp = response.json()
        timer.logger.debug('enemys:' + str(resp['result']))
        result = resp['result']
    else:
        timer.logger.error(f'get_enemy_condition filed!! http status_code {response.status_code}')

    return result
