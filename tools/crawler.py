import os
import re

import requests

# os.environ["https_proxy"] = "127.0.0.1:7890"
# os.environ["http_proxy"] = "127.0.0.1:7890"

UPDATE = True
URL = "https://www.zjsnrwiki.com/wiki/%E8%88%B0%E5%A8%98%E5%9B%BE%E9%89%B4#searchInput"
HTML_PATH = "../other_data/ship_name.html"
YAML_PATH = "../other_data/ship_name_example.yaml"
REPLACE = {
    1097: "长春",
    1125: "埃罗芒什",
    1068: "信赖",
    1456: "塔林",
    1169: "丹阳",
    1054: "重庆",
    1058: "奥希金斯",
    1185: "机灵",
    1408: "肥鱼",
    408: "肥鱼",
}


def get_source():
    if UPDATE:
        response = requests.get(URL)
        html = response.text
        with open(HTML_PATH, mode="w+", encoding="utf-8") as f:
            f.write(html)
    else:
        with open(HTML_PATH, mode="r", encoding="utf-8") as f:
            html = f.read()
    return html


def extract(str):
    re_rk_wsrwiki = r'<td width="162"><center><b>.{0,1000}</b></center></td>'
    re_name_wsrwiki = r'<td width="162" height="56"><center><b><a href="/wiki/.{0,1000} title=.{0,1000}</a></b></center></td>'
    res = ""
    rks = re.findall(re_rk_wsrwiki, str)
    names = re.findall(re_name_wsrwiki, str)
    # print(rks)
    # print(names)
    print(len(rks), len(names))

    for rk, name in zip(rks, names):
        rk = rk[30 : rk.find("</b>")].strip()  # 添加.strip()以去除可能的空格和换行符
        _title_idx = name.find("title") + 7
        name = name[_title_idx:]
        # 获取改后名字
        start_index = name.find(">") + 1
        end_index = name.find("<", start_index)
        substring = name[start_index:end_index]
        # 获取改前名字
        name = name[: name.index('"')]
        if substring != name:
            print(f"{name} : {substring}")
        if int(rk) in REPLACE:
            name = REPLACE[int(rk)]
        if name.find("(") != -1:
            _name = name[: name.find("(")]
        else:
            _name = name
        res += f"No.{rk}: # {name}\n"
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


with open(YAML_PATH, mode="w+", encoding="utf-8") as f:
    f.write(extract(get_source()))
