ALL_SHIP_TYPES = ["BB", "BC", "CL", "CV", "CA", "CVL", "NAP", "DD", "SS", "CLT", "KP", "CG"
                  "BM", "AV", "AADG", "ASDG", "BG", "CBG", "NO", "BBV", "CAV", "SC", "SAP"]
ALL_SHIP_TYPES_CN = ["轻巡", "驱逐", "航母", "潜艇", "导驱", "航战", "重巡", "防驱",
                     "战列", "战巡", "导驱", "导战", "大巡", "补给", "机场", "雷巡", "装母", "轻母", "补给", "重炮", "航巡",
                     "导巡", "防巡"]

BB = "BB"
BC = "BC"
CL = "CL"
CV = "CV"
CA = "CA"
CVL = "CVL"
NAP = "NAP"
DD = "DD"
SS = "SS"
CLT = "CLT"
BM = "BM"
AV = "AV"
AADG = "AADG"
ASDG = "ASDG"
BG = "BG"
CBG = "CBG"
NO = "NO"
BBV = "BBV"
CAV = "CAV"
SC = "SC"
SAP = "SAP"

"""舰船类型,参考游戏中显示的字符串,特殊和陌生的命名在下面给出,路基等单位暂时无数据
    NAP:常规补给舰,胖次期特殊点位刷六个那种,或者说除了掉胖次的之外的所有(包括我方)
    SAP:特殊补给舰,胖次期掉胖次的蓝色补给舰
    CBG:导弹巡洋舰
    CAV:航巡
    SC:炮潜
    BG:导战
    NO:该位置不存在舰船
"""

ALL_PAGES = {'map_page', 'main_page', 'decisive_battle_entrance', 'exercise_page', 'battle_page', 'expedition_page',
             'fight_prepare_page', 'bath_page', 'choose_repair_page', 'backyard_page', 'canteen_page',
             'options_page', 'build_page', 'destroy_page', 'develop_page', 'discard_page',
             'intensify_page', 'remake_page', 'skill_page', 'mission_page', 'support_set_page',
             'friend_page', 'friend_home_page', "decisive_battle_entrance"}
"""名字说明:
'fight_prepare_page':包含了快速修理,补给,综合属性等选项的界面
'friend_home_page':好友演习界面(从好友界面点进去之后的，好友的提督室)
"""

RESOURCE_NAME = {'oil', 'ammo', 'steel', 'aluminum', 'diamond', 'quick_repair', 'quick_build',
                 'ship_blueprint', 'equipment_blueprint', }

# 船舱容量,装备容量
PORT_FACILITIES = {'ship_limit', 'ship_amount', 'equipment_limit', 'equipment_amount'}

# 维修船坞,建造位,开发位
