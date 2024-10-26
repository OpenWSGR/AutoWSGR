import json
import os
from urllib import parse, request

import yaml


def load_config(config_path):
    with open(config_path, encoding='utf-8') as file:
        return yaml.safe_load(file)


def check_full_capacity_alert(config):
    page = request.urlopen(
        'http://miaotixing.com/trigger?'
        + str(parse.urlencode({'id': config['miao_code'], 'text': config['text'], 'type': 'json'})),
    )
    result = page.read()
    jsonObj = json.loads(result)
    if jsonObj['code'] == 0:
        print('成功')
    else:
        print('失败，错误代码：' + str(jsonObj['code']) + '，描述：' + jsonObj['msg'])


if __name__ == '__main__':
    # 获取miaotixing.py所在的目录路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建user_settings.yaml的相对路径
    config_path = os.path.join(current_dir, '..', '..', 'examples', 'user_settings.yaml')
    config = load_config(config_path)
    check_full_capacity_alert(config)
