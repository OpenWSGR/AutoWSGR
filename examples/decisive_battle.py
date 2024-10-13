import os

from autowsgr.fight import DecisiveBattle
from autowsgr.scripts.main import start_script

# 实现决战的自动化，使用前请先设置好下列参数。
# 本功能只支持使用副官哈巴库克，其他副官请自行更改游戏中的副官
# 本功能需要选出两艘在预设中的潜艇才会出击，如果选出了两艘潜艇没有出击或者一直sl请自行查看是否函数参数设置错误
# 决战攻略参考https://bbs.nga.cn/read.php?tid=23796937其中的哈巴库克开局攻略
timer = start_script(f"{os.path.dirname(os.path.abspath(__file__))}/user_settings.yaml")
decisive_battle = DecisiveBattle(
    timer,
    chapter=5,  # 设置为5则代表打E5，设置为6则代表打E6
    level1=[
        "鲃鱼",
        "U-1206",
        "射水鱼",
        "U-96",
        "U-1405",
        "U-47",
        "鹦鹉螺",
        "伊-25",
        "鹰",
        "达·芬奇",
    ],  # 打决战要优先选择的舰船，可以设置多个，此内容为出门点选择使用的船，后续编队时会尽量全部使用其中的船
    level2=[
        "U-81",
        "大青花鱼",
    ],  # 打决战要第二优先选择的舰船，可以设置多个，在第一个点不适用，后续如果有空位会选择这些舰船，后续会尽量全部使用level1其中的船
    flagship_priority=["U-1405", "U-47", "U-1206"],  # 旗舰优先选择的舰船，可以设置多个
    repair_level=1,  # 维修策略，1为中破修，2为大破修
    full_destroy=True,  # 是否船舱满了解装舰船（仅限决战）
)
decisive_battle.run_for_times(1)  # 数字为决战出击的次数
