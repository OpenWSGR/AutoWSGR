from airtest.core.cv import (MATCHING_METHODS, ST, InvalidMatchingMethodError,
                             TargetPos, Template)
from airtest.core.helper import G
from airtest.core.settings import Settings as ST
from utils.io import get_all_files

from .other_constants import ALL_UI, FIGHT_RESULTS


class MyTemplate(Template):
    def match_in(self, screen, this_methods=None):
        match_result = self._cv_match(screen, this_methods)
        G.LOGGING.debug("match result: %s", match_result)
        if not match_result:
            return None
        focus_pos = TargetPos().getXY(match_result, self.target_pos)
        return focus_pos

    def _cv_match(self, screen, this_methods=None):
        ori_image = self._imread()
        image = self._resize_image(ori_image, screen, ST.RESIZE_METHOD)
        ret = None
        if this_methods is None:
            this_methods = ST.CVSTRATEGY
        for method in this_methods:
            # get function definition and execute:
            func = MATCHING_METHODS.get(method, None)
            if func is None:
                raise InvalidMatchingMethodError(
                    "Undefined method in CVSTRATEGY: '%s', try 'kaze'/'brisk'/'akaze'/'orb'/'surf'/'sift'/'brief' instead." % method)
            else:
                if method in ["mstpl", "gmstpl"]:
                    ret = self._try_match(func, ori_image, screen, threshold=self.threshold, rgb=self.rgb, record_pos=self.record_pos,
                                          resolution=self.resolution, scale_max=self.scale_max, scale_step=self.scale_step)
                else:
                    ret = self._try_match(func, image, screen, threshold=self.threshold, rgb=self.rgb)
            if ret:
                break
        return ret


StartImage = ["", ]  # 启动用的图片
GameUI = ["", ]  # 基本UI
NumberImage = ["", ]  # 节点数字图片
ChapterImage = ["", ]  # 章节图片
SymbolImage = ["", ]  # 存储一些等待标志
TeamImage = ["", ]  # 队伍的图片
RepairImage = ["", ]  # 舰船修复相关的图片
ShipTypeImage = {}  # 舰船种类的汉字
FightImage = ["", ]  # 战斗相关图片
Image20220129 = ["", ]  # 20220129活动图片
Image20220415 = ["", ]  # 20220415活动图片
ConfirmImage = ["", ]  # 确认按钮图片
CancelImage = ["", ]  # 取消按钮的图片
BackImage = [""]  # 回退按钮的图片
ExerciseImages = {}
IdentifyImages = {}
ErrorImages = {}
FightResultImage = {}
DecisiveFightImages = {}
DecisiveObjectImage = {}
ChooseShipImages = ['', ]


all_images = get_all_files('./data/images', must='')


def make_tmplate(name=None, path=None, *args, **kwargs):
    MyTemplates = []
    if (name is not None):
        rec_pos = kwargs['rec_pos'] if "rec_pos" in kwargs else None
        return [MyTemplate(image, 0.9, resolution=(960, 540), record_pos=rec_pos) for image in all_images if (name in image)]

    return [MyTemplate(path, 0.9, resolution=(960, 540))]


def load_IdentifyImages():
    for page in ALL_UI:
        IdentifyImages[page] = make_tmplate(name=page)


def load_ErrorImages():
    ErrorImages['bad_network'] = make_tmplate("bad_network")


def load_other_images():
    PrePath = "./data/images/"

    StartImage.append(MyTemplate(PrePath + "StartImage\\1.PNG", resolution=(960, 540)))  # app ico
    StartImage.append(MyTemplate(PrePath + "StartImage\\2.PNG", resolution=(960, 540)))  # 开始游戏图标
    StartImage.append(MyTemplate(PrePath + "StartImage\\3.PNG", resolution=(960, 540)))  # 用户中心
    StartImage.append(MyTemplate(PrePath + "StartImage\\4.PNG", resolution=(960, 540)))  # 账号登录
    StartImage.append(MyTemplate(PrePath + "StartImage\\5.PNG", resolution=(960, 540)))  # 用户名或密码错误
    StartImage.append(MyTemplate(PrePath + "StartImage\\5.PNG", resolution=(960, 540)))  # 开始游戏图标

    ConfirmImage.append(MyTemplate(PrePath + "ConfirmImage\\1.PNG", resolution=(960, 540)))
    ConfirmImage.append(MyTemplate(PrePath + "ConfirmImage\\2.PNG", resolution=(960, 540)))
    ConfirmImage.append(MyTemplate(PrePath + "ConfirmImage\\3.PNG", resolution=(960, 540)))
    ConfirmImage.append(MyTemplate(PrePath + "ConfirmImage\\4.PNG", resolution=(960, 540)))
    # 各式各样的确认

    BackImage.append(MyTemplate(PrePath + "BackImage\\1.PNG", resolution=(960, 540)))
    BackImage.append(MyTemplate(PrePath + "BackImage\\2.PNG", resolution=(960, 540)))
    BackImage.append(MyTemplate(PrePath + "BackImage\\3.PNG", resolution=(960, 540)))
    BackImage.append(MyTemplate(PrePath + "BackImage\\4.PNG", resolution=(960, 540)))
    BackImage.append(MyTemplate(PrePath + "BackImage\\5.PNG", resolution=(960, 540)))
    BackImage.append(MyTemplate(PrePath + "BackImage\\6.PNG", resolution=(960, 540)))
    # 各式各样的回退

    GameUI.append(MyTemplate(PrePath + "GameUI\\1.PNG", resolution=(960, 540)))  # 已弃用
    GameUI.append(MyTemplate(PrePath + "GameUI\\2.PNG", resolution=(960, 540)))  # 已弃用
    GameUI.append(MyTemplate(PrePath + "GameUI\\3.PNG", resolution=(960, 540)))  # 出征图标
    GameUI.append(MyTemplate(PrePath + "GameUI\\4.PNG", resolution=(960, 540)))  # 已弃用
    GameUI.append(MyTemplate(PrePath + "GameUI\\5.PNG", resolution=(960, 540)))  # 已弃用
    GameUI.append(MyTemplate(PrePath + "GameUI\\6.PNG", resolution=(960, 540)))  # 远征收获奖励
    GameUI.append(MyTemplate(PrePath + "GameUI\\7.PNG", resolution=(960, 540)))  # 确认收获奖励
    GameUI.append(MyTemplate(PrePath + "GameUI\\8.PNG", resolution=(960, 540)))  # 解装卸装
    GameUI.append(MyTemplate(PrePath + "GameUI\\9.PNG", resolution=(960, 540)))  # 已弃用
    GameUI.append(MyTemplate(PrePath + "GameUI\\10.PNG", resolution=(960, 540)))  # 已弃用
    GameUI.append(MyTemplate(PrePath + "GameUI\\11.PNG", resolution=(960, 540)))  # 已弃用
    GameUI.append(MyTemplate(PrePath + "GameUI\\12.PNG", resolution=(960, 540)))  # 任务领奖
    GameUI.append(MyTemplate(PrePath + "GameUI\\13.PNG", resolution=(960, 540)))  # 浴场选择舰船
    GameUI.append(MyTemplate(PrePath + "GameUI\\14.PNG", resolution=(960, 540)))  # 浴场全部修理
    GameUI.append(MyTemplate(PrePath + "GameUI\\15.PNG", resolution=(960, 540)))  # 领取奖励
    GameUI.append(MyTemplate(PrePath + "GameUI\\16.PNG", resolution=(960, 540)))  # 决战小地图右下角"编队  出征"
    GameUI.append(MyTemplate(PrePath + "GameUI\\17.PNG", resolution=(960, 540)))  # 决战小地图选择舰船"刷新  关闭"

    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\1.PNG", resolution=(960, 540)))
    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\2.PNG", resolution=(960, 540)))
    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\3.PNG", resolution=(960, 540)))
    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\4.PNG", resolution=(960, 540)))
    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\5.PNG", resolution=(960, 540)))
    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\6.PNG", resolution=(960, 540)))
    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\7.PNG", resolution=(960, 540)))
    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\8.PNG", resolution=(960, 540)))
    ChapterImage.append(MyTemplate(PrePath + "ChapterImage\\9.PNG", resolution=(960, 540)))

    NumberImage.append(MyTemplate(PrePath + "number\\1.PNG", resolution=(960, 540)))
    NumberImage.append(MyTemplate(PrePath + "number\\2.PNG", resolution=(960, 540)))
    NumberImage.append(MyTemplate(PrePath + "number\\3.PNG", resolution=(960, 540)))
    NumberImage.append(MyTemplate(PrePath + "number\\4.PNG", resolution=(960, 540)))
    NumberImage.append(MyTemplate(PrePath + "number\\5.PNG", resolution=(960, 540)))
    NumberImage.append(MyTemplate(PrePath + "number\\6.PNG", resolution=(960, 540)))

    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\1.PNG", resolution=(960, 540)))  # 出征准备
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\2.PNG", resolution=(960, 540)))  # 演习
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\3.PNG", resolution=(960, 540)))  # 船坞已满
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\4.PNG", resolution=(960, 540)))  # "阵"
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\5.PNG", resolution=(960, 540)))  # 解装
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\6.PNG", resolution=(960, 540)))  # 添加
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\7.PNG", resolution=(960, 540)))  # 选择舰船
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\8.PNG", resolution=(960, 540)))  # 战斗掉落舰船页面标志
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\9.PNG", resolution=(960, 540)))  # 战役次数用尽
    SymbolImage.append(MyTemplate(PrePath + "SymbolImage\\10.PNG", resolution=(960, 540)))  # 正在重新连接服务器

    TeamImage.append(MyTemplate(PrePath + "TeamImage\\1.PNG", resolution=(960, 540)))
    TeamImage.append(MyTemplate(PrePath + "TeamImage\\2.PNG", resolution=(960, 540)))
    TeamImage.append(MyTemplate(PrePath + "TeamImage\\3.PNG", resolution=(960, 540)))
    TeamImage.append(MyTemplate(PrePath + "TeamImage\\4.PNG", resolution=(960, 540)))

    ChooseShipImages.append(MyTemplate(PrePath + "ChooseShipImages\\1.PNG", resolution=(960, 540)))  # 有标记选择舰船界面
    ChooseShipImages.append(MyTemplate(PrePath + "ChooseShipImages\\2.PNG", resolution=(960, 540)))  # 无标记选择舰船界面
    ChooseShipImages.append(MyTemplate(PrePath + "ChooseShipImages\\3.PNG", resolution=(960, 540)))  # 文本框确认

    FightImage.append(MyTemplate(PrePath + "FightImage\\1.PNG", resolution=(960, 540)))  # 选择阵型
    FightImage.append(MyTemplate(PrePath + "FightImage\\2.PNG", resolution=(960, 540)))  # 开始战斗
    FightImage.append(MyTemplate(PrePath + "FightImage\\3.PNG", resolution=(960, 540)))  # 点击继续
    FightImage.append(MyTemplate(PrePath + "FightImage\\4.PNG", resolution=(960, 540)))  # 大破回港
    FightImage.append(MyTemplate(PrePath + "FightImage\\5.PNG", resolution=(960, 540)))  # 前进回港
    FightImage.append(MyTemplate(PrePath + "FightImage\\6.PNG", resolution=(960, 540)))  # 追击回港
    FightImage.append(MyTemplate(PrePath + "FightImage\\7.PNG", resolution=(960, 540)))  # 舰船图标1
    FightImage.append(MyTemplate(PrePath + "FightImage\\8.PNG", resolution=(960, 540)))  # 舰船图标2
    FightImage.append(MyTemplate(PrePath + "FightImage\\9.PNG", resolution=(960, 540)))  # 困难模式
    FightImage.append(MyTemplate(PrePath + "FightImage\\10.PNG", resolution=(960, 540)))  # 选择战况
    FightImage.append(MyTemplate(PrePath + "FightImage\\11.PNG", resolution=(960, 540)))  # 自动补给标志
    FightImage.append(MyTemplate(PrePath + "FightImage\\12.PNG", resolution=(960, 540)))  # 自动补给标志
    FightImage.append(MyTemplate(PrePath + "FightImage\\13.PNG", resolution=(960, 540)))  # 战术迂回
    FightImage.append(MyTemplate(PrePath + "FightImage\\14.PNG", resolution=(960, 540)))  # MVP
    FightImage.append(MyTemplate(PrePath + "FightImage\\15.PNG", resolution=(960, 540)))  # 简单模式
    FightImage.append(MyTemplate(PrePath + "FightImage\\16.PNG", resolution=(960, 540)))  # 战役 点击继续

    RepairImage.append(MyTemplate(PrePath + "RepairImage\\1.PNG", resolution=(960, 540)))  # 修理中


def load_fightresult_images():
    for result in FIGHT_RESULTS:
        FightResultImage[result] = make_tmplate('fight_result/' + result)


def load_ExerciseImages():
    ExerciseImages['rival_info'] = make_tmplate(path='data/images/exercise/rival_info.PNG')


def load_images():
    load_ExerciseImages()
    load_ErrorImages()
    load_IdentifyImages()
    load_fightresult_images()
    load_other_images()
