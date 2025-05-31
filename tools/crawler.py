import re

import requests


# os.environ["https_proxy"] = "127.0.0.1:7890"
# os.environ["http_proxy"] = "127.0.0.1:7890"

UPDATE = True
URL = 'https://www.zjsnrwiki.com/wiki/%E8%88%B0%E5%A8%98%E5%9B%BE%E9%89%B4#searchInput'
HTML_PATH = './ship_name.html'
YAML_PATH = './ship_name_example.yaml'


def get_source():
    if UPDATE:
        response = requests.get(URL, timeout=5)
        html = response.text
        with open(HTML_PATH, mode='w+', encoding='utf-8') as f:
            f.write(html)
    else:
        with open(HTML_PATH, encoding='utf-8') as f:
            html = f.read()
    return html


def extract(str):
    re_rk_wsrwiki = r'<td width="162px"><center><b>(.*?)</b></center></td>'
    re_name_wsrwiki = (
        r'<td width="162px" height="56px"><center><b><a [^>]*>(.*?)</a></b></center></td>'
    )
    res = ''
    rks = re.findall(re_rk_wsrwiki, str)
    names = re.findall(re_name_wsrwiki, str)
    # print(rks)
    # print(names)
    print(len(rks), len(names))

    for rk, name in zip(rks, names, strict=False):
        rk = rk[3:].strip()  # 添加.strip()以去除可能的空格和换行符
        # 获取舰船名字
        name = name.strip()
        _name = name[: name.find('(')] if name.find('(') != -1 else name
        res += f'No.{rk}: # {name}\n'
        res += f'  - "{_name}"\n'

    res += """Other: # 战例
  - 肌肉记忆
  - 长跑训练
  - 航空训练
  - 训练的结晶
  - 黑科技
  - 防空伞
  - 守护之盾
  - 抱头蹲防
  - 关键一击
  - 久远的加护"""
    return res


with open(YAML_PATH, mode='w+', encoding='utf-8') as f:
    f.write(extract(get_source()))
