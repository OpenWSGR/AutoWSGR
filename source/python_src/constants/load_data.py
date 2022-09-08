
from utils.api_image import relative_to_absolute
from controller.run_timer import MyTemplate
from utils.io import get_all_files

from constants.image_templates import (BackImage, ChapterImage,
                                       ChooseShipImages, ConfirmImage,
                                       ErrorImages, FightImage, ExerciseImages,
                                       FightResultImage, GameUI,
                                       IdentifyImages, NumberImage,
                                       RepairImage, StartImage, SymbolImage,
                                       TeamImage)
from constants.keypoint_info import POINT_POSITION
from constants.other_constants import ALL_UI, FIGHT_RESULTS

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


def load_point_positions():

    POINT_POSITION[(1, 1, 'A')] = (284-1, 286-35)
    POINT_POSITION[(1, 1, 'B')] = (391-1, 182-35)
    POINT_POSITION[(1, 1, 'C')] = (396-1, 318-35)
    POINT_POSITION[(1, 2, 'A')] = (255-1, 278-35)
    POINT_POSITION[(1, 2, 'B')] = (369-1, 346-35)
    POINT_POSITION[(1, 2, 'C')] = (353-1, 187-35)
    POINT_POSITION[(1, 2, 'D')] = (501-1, 401-35)
    POINT_POSITION[(1, 3, 'A')] = (337-1, 323-35)
    POINT_POSITION[(1, 3, 'B')] = (435-1, 438-35)
    POINT_POSITION[(1, 3, 'C')] = (475-1, 306-35)
    POINT_POSITION[(1, 3, 'D')] = (593-1, 381-35)
    POINT_POSITION[(1, 3, 'E')] = (425-1, 186-35)
    POINT_POSITION[(1, 3, 'F')] = (629-1, 218-35)
    POINT_POSITION[(1, 4, 'A')] = (498-1, 398-35)
    POINT_POSITION[(1, 4, 'B')] = (666-1, 327-35)
    POINT_POSITION[(1, 4, 'C')] = (384-1, 361-35)
    POINT_POSITION[(1, 4, 'D')] = (612-1, 178-35)
    POINT_POSITION[(1, 4, 'E')] = (225-1, 350-35)
    POINT_POSITION[(1, 4, 'F')] = (402-1, 218-35)
    POINT_POSITION[(1, 4, 'G')] = (281-1, 149-35)
    POINT_POSITION[(1, 5, 'A')] = (590-1, 251-35)
    POINT_POSITION[(2, 1, 'A')] = (331-1, 139-35)
    POINT_POSITION[(2, 1, 'B')] = (246-1, 271-35)
    POINT_POSITION[(2, 1, 'C')] = (470-1, 174-35)
    POINT_POSITION[(2, 1, 'D')] = (311-1, 409-35)
    POINT_POSITION[(2, 1, 'E')] = (556-1, 304-35)
    POINT_POSITION[(2, 1, 'F')] = (488-1, 446-35)
    POINT_POSITION[(2, 2, 'A')] = (548-1, 259-35)
    POINT_POSITION[(2, 2, 'B')] = (399-1, 245-35)
    POINT_POSITION[(2, 2, 'C')] = (675-1, 214-35)
    POINT_POSITION[(2, 2, 'D')] = (592-1, 401-35)
    POINT_POSITION[(2, 2, 'E')] = (429-1, 372-35)
    POINT_POSITION[(2, 2, 'F')] = (244-1, 232-35)
    POINT_POSITION[(2, 2, 'G')] = (345-1, 476-35)
    POINT_POSITION[(2, 2, 'H')] = (199-1, 113-35)
    POINT_POSITION[(2, 3, 'A')] = (132-1, 338-35)
    POINT_POSITION[(2, 3, 'B')] = (324-1, 432-35)
    POINT_POSITION[(2, 3, 'C')] = (192-1, 210-35)
    POINT_POSITION[(2, 3, 'D')] = (349-1, 285-35)
    POINT_POSITION[(2, 3, 'E')] = (559-1, 480-35)
    POINT_POSITION[(2, 3, 'F')] = (338-1, 116-35)
    POINT_POSITION[(2, 3, 'G')] = (458-1, 210-35)
    POINT_POSITION[(2, 3, 'H')] = (698-1, 443-35)
    POINT_POSITION[(2, 3, 'I')] = (519-1, 95-35)
    POINT_POSITION[(2, 3, 'J')] = (673-1, 202-35)
    POINT_POSITION[(2, 3, 'K')] = (789-1, 289-35)
    POINT_POSITION[(2, 4, 'A')] = (113-1, 375-35)
    POINT_POSITION[(2, 4, 'B')] = (286-1, 387-35)
    POINT_POSITION[(2, 4, 'C')] = (240-1, 203-35)
    POINT_POSITION[(2, 4, 'D')] = (439-1, 323-35)
    POINT_POSITION[(2, 4, 'E')] = (413-1, 424-35)
    POINT_POSITION[(2, 4, 'F')] = (443-1, 225-35)
    POINT_POSITION[(2, 4, 'G')] = (570-1, 378-35)
    POINT_POSITION[(2, 4, 'H')] = (514-1, 491-35)
    POINT_POSITION[(2, 4, 'I')] = (526-1, 126-35)
    POINT_POSITION[(2, 4, 'J')] = (613-1, 221-35)
    POINT_POSITION[(2, 4, 'K')] = (748-1, 439-35)
    POINT_POSITION[(2, 4, 'L')] = (815-1, 169-35)
    POINT_POSITION[(2, 5, 'A')] = (203-1, 113-35)
    POINT_POSITION[(2, 5, 'B')] = (339-1, 162-35)
    POINT_POSITION[(2, 5, 'C')] = (458-1, 124-35)
    POINT_POSITION[(2, 5, 'D')] = (390-1, 252-35)
    POINT_POSITION[(2, 5, 'E')] = (214-1, 315-35)
    POINT_POSITION[(2, 5, 'F')] = (645-1, 79-35)
    POINT_POSITION[(2, 5, 'G')] = (612-1, 195-35)
    POINT_POSITION[(2, 5, 'H')] = (465-1, 334-35)
    POINT_POSITION[(2, 5, 'I')] = (459-1, 410-35)
    POINT_POSITION[(2, 5, 'J')] = (781-1, 169-35)
    POINT_POSITION[(2, 5, 'K')] = (609-1, 289-35)
    POINT_POSITION[(2, 5, 'L')] = (744-1, 400-35)
    POINT_POSITION[(2, 5, 'M')] = (626-1, 483-35)
    POINT_POSITION[(2, 5, 'N')] = (297-1, 498-35)
    POINT_POSITION[(2, 5, 'O')] = (826-1, 311-35)
    POINT_POSITION[(2, 6, 'A')] = (136-1, 319-35)
    POINT_POSITION[(2, 6, 'B')] = (339-1, 492-35)
    POINT_POSITION[(2, 6, 'C')] = (113-1, 169-35)
    POINT_POSITION[(2, 6, 'D')] = (285-1, 267-35)
    POINT_POSITION[(2, 6, 'E')] = (361-1, 379-35)
    POINT_POSITION[(2, 6, 'F')] = (518-1, 405-35)
    POINT_POSITION[(2, 6, 'G')] = (360-1, 109-35)
    POINT_POSITION[(2, 6, 'H')] = (653-1, 424-35)
    POINT_POSITION[(2, 6, 'I')] = (553-1, 122-35)
    POINT_POSITION[(2, 6, 'J')] = (504-1, 214-35)
    POINT_POSITION[(2, 6, 'K')] = (632-1, 278-35)
    POINT_POSITION[(2, 6, 'L')] = (706-1, 108-35)
    POINT_POSITION[(2, 6, 'M')] = (840-1, 327-35)
    POINT_POSITION[(3, 1, 'A')] = (436-1, 117-35)
    POINT_POSITION[(3, 1, 'B')] = (380-1, 207-35)
    POINT_POSITION[(3, 1, 'C')] = (300-1, 146-35)
    POINT_POSITION[(3, 1, 'D')] = (645-1, 259-35)
    POINT_POSITION[(3, 1, 'E')] = (387-1, 304-35)
    POINT_POSITION[(3, 1, 'F')] = (188-1, 259-35)
    POINT_POSITION[(3, 1, 'G')] = (488-1, 371-35)
    POINT_POSITION[(3, 1, 'H')] = (210-1, 408-35)
    POINT_POSITION[(3, 1, 'I')] = (376-1, 463-35)
    POINT_POSITION[(3, 2, 'A')] = (788-1, 221-35)
    POINT_POSITION[(3, 2, 'B')] = (624-1, 282-35)
    POINT_POSITION[(3, 2, 'C')] = (600-1, 199-35)
    POINT_POSITION[(3, 2, 'D')] = (709-1, 327-35)
    POINT_POSITION[(3, 2, 'E')] = (466-1, 311-35)
    POINT_POSITION[(3, 2, 'F')] = (683-1, 454-35)
    POINT_POSITION[(3, 2, 'G')] = (443-1, 461-35)
    POINT_POSITION[(3, 3, 'A')] = (788-1, 297-35)
    POINT_POSITION[(3, 3, 'B')] = (714-1, 244-35)
    POINT_POSITION[(3, 3, 'C')] = (657-1, 375-35)
    POINT_POSITION[(3, 3, 'D')] = (592-1, 255-35)
    POINT_POSITION[(3, 3, 'E')] = (466-1, 161-35)
    POINT_POSITION[(3, 3, 'F')] = (540-1, 472-35)
    POINT_POSITION[(3, 3, 'G')] = (533-1, 356-35)
    POINT_POSITION[(3, 3, 'H')] = (308-1, 259-35)
    POINT_POSITION[(3, 3, 'I')] = (444-1, 305-35)
    POINT_POSITION[(3, 3, 'J')] = (354-1, 416-35)
    POINT_POSITION[(3, 3, 'K')] = (137-1, 424-35)
    POINT_POSITION[(3, 4, 'A')] = (661-1, 209-35)
    POINT_POSITION[(3, 4, 'B')] = (639-1, 346-35)
    POINT_POSITION[(3, 4, 'C')] = (540-1, 255-35)
    POINT_POSITION[(3, 4, 'D')] = (525-1, 439-35)
    POINT_POSITION[(3, 4, 'E')] = (428-1, 263-35)
    POINT_POSITION[(3, 4, 'F')] = (360-1, 476-35)
    POINT_POSITION[(3, 4, 'G')] = (383-1, 364-35)
    POINT_POSITION[(3, 4, 'H')] = (210-1, 333-35)
    POINT_POSITION[(3, 4, 'I')] = (256-1, 227-35)
    POINT_POSITION[(3, 4, 'J')] = (129-1, 139-35)
    POINT_POSITION[(4, 1, 'A')] = (642-1, 267-35)
    POINT_POSITION[(4, 1, 'B')] = (609-1, 181-35)
    POINT_POSITION[(4, 1, 'C')] = (585-1, 379-35)
    POINT_POSITION[(4, 1, 'D')] = (487-1, 221-35)
    POINT_POSITION[(4, 1, 'E')] = (661-1, 461-35)
    POINT_POSITION[(4, 1, 'F')] = (446-1, 311-35)
    POINT_POSITION[(4, 1, 'G')] = (248-1, 266-35)
    POINT_POSITION[(4, 1, 'H')] = (795-1, 446-35)
    POINT_POSITION[(4, 1, 'I')] = (264-1, 463-35)
    POINT_POSITION[(4, 1, 'J')] = (91-1, 311-35)
    POINT_POSITION[(4, 2, 'A')] = (631-1, 409-35)
    POINT_POSITION[(4, 2, 'B')] = (759-1, 282-35)
    POINT_POSITION[(4, 2, 'C')] = (518-1, 383-35)
    POINT_POSITION[(4, 2, 'D')] = (637-1, 311-35)
    POINT_POSITION[(4, 2, 'E')] = (297-1, 341-35)
    POINT_POSITION[(4, 2, 'F')] = (552-1, 176-35)
    POINT_POSITION[(4, 2, 'G')] = (252-1, 443-35)
    POINT_POSITION[(4, 2, 'H')] = (402-1, 224-35)
    POINT_POSITION[(4, 2, 'I')] = (324-1, 118-35)
    POINT_POSITION[(4, 2, 'J')] = (211-1, 139-35)
    POINT_POSITION[(4, 3, 'A')] = (751-1, 274-35)
    POINT_POSITION[(4, 3, 'B')] = (624-1, 143-35)
    POINT_POSITION[(4, 3, 'C')] = (615-1, 300-35)
    POINT_POSITION[(4, 3, 'D')] = (345-1, 124-35)
    POINT_POSITION[(4, 3, 'E')] = (488-1, 285-35)
    POINT_POSITION[(4, 3, 'F')] = (199-1, 289-35)
    POINT_POSITION[(4, 3, 'G')] = (357-1, 281-35)
    POINT_POSITION[(4, 3, 'H')] = (154-1, 461-35)
    POINT_POSITION[(4, 4, 'A')] = (601-1, 464-35)
    POINT_POSITION[(4, 4, 'B')] = (669-1, 327-35)
    POINT_POSITION[(4, 4, 'C')] = (304-1, 454-35)
    POINT_POSITION[(4, 4, 'D')] = (424-1, 432-35)
    POINT_POSITION[(4, 4, 'E')] = (552-1, 311-35)
    POINT_POSITION[(4, 4, 'F')] = (195-1, 363-35)
    POINT_POSITION[(4, 4, 'G')] = (428-1, 232-35)
    POINT_POSITION[(4, 4, 'H')] = (525-1, 168-35)
    POINT_POSITION[(4, 4, 'I')] = (140-1, 261-35)
    POINT_POSITION[(4, 4, 'J')] = (399-1, 128-35)
    POINT_POSITION[(4, 4, 'K')] = (261-1, 203-35)
    POINT_POSITION[(4, 4, 'L')] = (132-1, 127-35)
    POINT_POSITION[(5, 1, 'A')] = (683-1, 394-35)
    POINT_POSITION[(5, 1, 'B')] = (770-1, 207-35)
    POINT_POSITION[(5, 1, 'C')] = (495-1, 469-35)
    POINT_POSITION[(5, 1, 'D')] = (517-1, 251-35)
    POINT_POSITION[(5, 1, 'E')] = (117-1, 371-35)
    POINT_POSITION[(5, 1, 'F')] = (255-1, 296-35)
    POINT_POSITION[(5, 1, 'G')] = (345-1, 116-35)
    POINT_POSITION[(5, 1, 'H')] = (135-1, 101-35)
    POINT_POSITION[(5, 2, 'A')] = (676-1, 469-35)
    POINT_POSITION[(5, 2, 'B')] = (654-1, 301-35)
    POINT_POSITION[(5, 2, 'C')] = (840-1, 244-35)
    POINT_POSITION[(5, 2, 'D')] = (405-1, 424-35)
    POINT_POSITION[(5, 2, 'E')] = (484-1, 293-35)
    POINT_POSITION[(5, 2, 'F')] = (585-1, 116-35)
    POINT_POSITION[(5, 2, 'G')] = (180-1, 487-35)
    POINT_POSITION[(5, 2, 'H')] = (267-1, 274-35)
    POINT_POSITION[(5, 2, 'I')] = (309-1, 118-35)
    POINT_POSITION[(5, 2, 'J')] = (99-1, 161-35)
    POINT_POSITION[(5, 3, 'A')] = (713-1, 357-35)
    POINT_POSITION[(5, 3, 'B')] = (631-1, 166-35)
    POINT_POSITION[(5, 3, 'C')] = (773-1, 465-35)
    POINT_POSITION[(5, 3, 'D')] = (540-1, 311-35)
    POINT_POSITION[(5, 3, 'E')] = (571-1, 461-35)
    POINT_POSITION[(5, 3, 'F')] = (477-1, 195-35)
    POINT_POSITION[(5, 3, 'G')] = (282-1, 412-35)
    POINT_POSITION[(5, 3, 'H')] = (180-1, 236-35)
    POINT_POSITION[(5, 4, 'A')] = (616-1, 267-35)
    POINT_POSITION[(5, 4, 'B')] = (541-1, 98-35)
    POINT_POSITION[(5, 4, 'C')] = (691-1, 416-35)
    POINT_POSITION[(5, 4, 'D')] = (322-1, 191-35)
    POINT_POSITION[(5, 4, 'E')] = (488-1, 476-35)
    POINT_POSITION[(5, 4, 'F')] = (450-1, 371-35)
    POINT_POSITION[(5, 4, 'G')] = (237-1, 412-35)
    POINT_POSITION[(5, 4, 'H')] = (83-1, 244-35)
    POINT_POSITION[(5, 5, 'A')] = (766-1, 454-35)
    POINT_POSITION[(5, 5, 'B')] = (684-1, 334-35)
    POINT_POSITION[(5, 5, 'C')] = (593-1, 124-35)
    POINT_POSITION[(5, 5, 'D')] = (510-1, 454-35)
    POINT_POSITION[(5, 5, 'E')] = (466-1, 259-35)
    POINT_POSITION[(5, 5, 'F')] = (421-1, 119-35)
    POINT_POSITION[(5, 5, 'G')] = (255-1, 457-35)
    POINT_POSITION[(5, 5, 'H')] = (259-1, 299-35)
    POINT_POSITION[(5, 5, 'I')] = (91-1, 231-35)
    POINT_POSITION[(6, 1, 'A')] = (391-1, 469-35)
    POINT_POSITION[(6, 1, 'B')] = (526-1, 357-35)
    POINT_POSITION[(6, 1, 'C')] = (630-1, 341-35)
    POINT_POSITION[(6, 1, 'D')] = (232-1, 372-35)
    POINT_POSITION[(6, 1, 'E')] = (391-1, 371-35)
    POINT_POSITION[(6, 1, 'F')] = (465-1, 229-35)
    POINT_POSITION[(6, 1, 'G')] = (139-1, 476-35)
    POINT_POSITION[(6, 1, 'H')] = (248-1, 229-35)
    POINT_POSITION[(6, 1, 'I')] = (444-1, 118-35)
    POINT_POSITION[(6, 1, 'J')] = (84-1, 319-35)
    POINT_POSITION[(6, 1, 'K')] = (144-1, 154-35)
    POINT_POSITION[(6, 1, 'L')] = (331-1, 101-35)
    POINT_POSITION[(6, 2, 'A')] = (68-1, 237-35)
    POINT_POSITION[(6, 2, 'B')] = (177-1, 342-35)
    POINT_POSITION[(6, 2, 'C')] = (390-1, 472-35)
    POINT_POSITION[(6, 2, 'D')] = (240-1, 177-35)
    POINT_POSITION[(6, 2, 'E')] = (316-1, 251-35)
    POINT_POSITION[(6, 2, 'F')] = (518-1, 371-35)
    POINT_POSITION[(6, 2, 'G')] = (428-1, 168-35)
    POINT_POSITION[(6, 2, 'H')] = (488-1, 274-35)
    POINT_POSITION[(6, 2, 'I')] = (691-1, 325-35)
    POINT_POSITION[(6, 2, 'J')] = (579-1, 124-35)
    POINT_POSITION[(6, 2, 'K')] = (632-1, 218-35)
    POINT_POSITION[(6, 2, 'L')] = (766-1, 221-35)
    POINT_POSITION[(6, 2, 'M')] = (832-1, 101-35)
    POINT_POSITION[(6, 3, 'A')] = (406-1, 469-35)
    POINT_POSITION[(6, 3, 'B')] = (294-1, 297-35)
    POINT_POSITION[(6, 3, 'C')] = (165-1, 281-35)
    POINT_POSITION[(6, 3, 'D')] = (562-1, 443-35)
    POINT_POSITION[(6, 3, 'E')] = (451-1, 233-35)
    POINT_POSITION[(6, 3, 'F')] = (346-1, 104-35)
    POINT_POSITION[(6, 3, 'G')] = (698-1, 326-35)
    POINT_POSITION[(6, 3, 'H')] = (638-1, 252-35)
    POINT_POSITION[(6, 3, 'I')] = (541-1, 152-35)
    POINT_POSITION[(6, 3, 'J')] = (845-1, 157-35)
    POINT_POSITION[(6, 4, 'A')] = (139-1, 296-35)
    POINT_POSITION[(6, 4, 'B')] = (380-1, 297-35)
    POINT_POSITION[(6, 4, 'C')] = (240-1, 165-35)
    POINT_POSITION[(6, 4, 'D')] = (217-1, 416-35)
    POINT_POSITION[(6, 4, 'E')] = (421-1, 469-35)
    POINT_POSITION[(6, 4, 'F')] = (428-1, 138-35)
    POINT_POSITION[(6, 4, 'G')] = (511-1, 326-35)
    POINT_POSITION[(6, 4, 'H')] = (600-1, 232-35)
    POINT_POSITION[(6, 4, 'I')] = (635-1, 103-35)
    POINT_POSITION[(6, 4, 'J')] = (774-1, 319-35)
    POINT_POSITION[(6, 4, 'K')] = (662-1, 462-35)
    POINT_POSITION[(6, 4, 'L')] = (901-1, 439-35)
    POINT_POSITION[(7, 1, 'A')] = (713-1, 424-35)
    POINT_POSITION[(7, 1, 'B')] = (669-1, 200-35)
    POINT_POSITION[(7, 1, 'C')] = (582-1, 372-35)
    POINT_POSITION[(7, 1, 'D')] = (544-1, 236-35)
    POINT_POSITION[(7, 1, 'E')] = (601-1, 109-35)
    POINT_POSITION[(7, 1, 'F')] = (435-1, 446-35)
    POINT_POSITION[(7, 1, 'G')] = (435-1, 334-35)
    POINT_POSITION[(7, 1, 'H')] = (417-1, 199-35)
    POINT_POSITION[(7, 1, 'I')] = (298-1, 317-35)
    POINT_POSITION[(7, 1, 'J')] = (234-1, 124-35)
    POINT_POSITION[(7, 1, 'K')] = (272-1, 214-35)
    POINT_POSITION[(7, 1, 'L')] = (275-1, 465-35)
    POINT_POSITION[(7, 1, 'M')] = (217-1, 375-35)
    POINT_POSITION[(7, 1, 'N')] = (91-1, 273-35)
    POINT_POSITION[(7, 2, 'A')] = (518-1, 312-35)
    POINT_POSITION[(7, 2, 'B')] = (631-1, 252-35)
    POINT_POSITION[(7, 2, 'C')] = (503-1, 424-35)
    POINT_POSITION[(7, 2, 'D')] = (386-1, 357-35)
    POINT_POSITION[(7, 2, 'E')] = (458-1, 184-35)
    POINT_POSITION[(7, 2, 'F')] = (758-1, 214-35)
    POINT_POSITION[(7, 2, 'G')] = (660-1, 124-35)
    POINT_POSITION[(7, 2, 'H')] = (270-1, 319-35)
    POINT_POSITION[(7, 2, 'I')] = (335-1, 478-35)
    POINT_POSITION[(7, 2, 'J')] = (129-1, 371-35)
    POINT_POSITION[(7, 2, 'K')] = (257-1, 165-35)
    POINT_POSITION[(7, 2, 'L')] = (875-1, 135-35)
    POINT_POSITION[(7, 2, 'M')] = (112-1, 131-35)
    POINT_POSITION[(7, 3, 'A')] = (646-1, 439-35)
    POINT_POSITION[(7, 3, 'B')] = (661-1, 312-35)
    POINT_POSITION[(7, 3, 'C')] = (754-1, 180-35)
    POINT_POSITION[(7, 3, 'D')] = (476-1, 480-35)
    POINT_POSITION[(7, 3, 'E')] = (544-1, 379-35)
    POINT_POSITION[(7, 3, 'F')] = (563-1, 259-35)
    POINT_POSITION[(7, 3, 'G')] = (615-1, 120-35)
    POINT_POSITION[(7, 3, 'H')] = (323-1, 432-35)
    POINT_POSITION[(7, 3, 'I')] = (365-1, 366-35)
    POINT_POSITION[(7, 3, 'J')] = (429-1, 214-35)
    POINT_POSITION[(7, 3, 'K')] = (493-1, 109-35)
    POINT_POSITION[(7, 3, 'L')] = (211-1, 289-35)
    POINT_POSITION[(7, 3, 'M')] = (315-1, 147-35)
    POINT_POSITION[(7, 3, 'N')] = (121-1, 176-35)
    POINT_POSITION[(7, 4, 'A')] = (758-1, 293-35)
    POINT_POSITION[(7, 4, 'B')] = (684-1, 106-35)
    POINT_POSITION[(7, 4, 'C')] = (690-1, 382-35)
    POINT_POSITION[(7, 4, 'D')] = (555-1, 240-35)
    POINT_POSITION[(7, 4, 'E')] = (500-1, 135-35)
    POINT_POSITION[(7, 4, 'F')] = (604-1, 442-35)
    POINT_POSITION[(7, 4, 'G')] = (416-1, 236-35)
    POINT_POSITION[(7, 4, 'H')] = (383-1, 120-35)
    POINT_POSITION[(7, 4, 'I')] = (478-1, 475-35)
    POINT_POSITION[(7, 4, 'J')] = (384-1, 428-35)
    POINT_POSITION[(7, 4, 'K')] = (339-1, 356-35)
    POINT_POSITION[(7, 4, 'L')] = (301-1, 172-35)
    POINT_POSITION[(7, 4, 'M')] = (176-1, 172-35)
    POINT_POSITION[(7, 5, 'A')] = (766-1, 434-35)
    POINT_POSITION[(7, 5, 'B')] = (736-1, 286-35)
    POINT_POSITION[(7, 5, 'C')] = (630-1, 469-35)
    POINT_POSITION[(7, 5, 'D')] = (630-1, 330-35)
    POINT_POSITION[(7, 5, 'E')] = (608-1, 225-35)
    POINT_POSITION[(7, 5, 'F')] = (705-1, 150-35)
    POINT_POSITION[(7, 5, 'G')] = (450-1, 480-35)
    POINT_POSITION[(7, 5, 'H')] = (499-1, 338-35)
    POINT_POSITION[(7, 5, 'I')] = (463-1, 175-35)
    POINT_POSITION[(7, 5, 'J')] = (564-1, 113-35)
    POINT_POSITION[(7, 5, 'K')] = (295-1, 457-35)
    POINT_POSITION[(7, 5, 'L')] = (369-1, 322-35)
    POINT_POSITION[(7, 5, 'M')] = (412-1, 105-35)
    POINT_POSITION[(7, 5, 'N')] = (233-1, 287-35)
    POINT_POSITION[(7, 5, 'O')] = (99-1, 232-35)
    POINT_POSITION[(7, 5, 'P')] = (144-1, 379-35)
    POINT_POSITION[(7, 5, 'Q')] = (99-1, 235-35)
    POINT_POSITION[(8, 1, 'A')] = (221-1, 241-35)
    POINT_POSITION[(8, 1, 'B')] = (312-1, 133-35)
    POINT_POSITION[(8, 1, 'C')] = (281-1, 374-35)
    POINT_POSITION[(8, 1, 'D')] = (398-1, 309-35)
    POINT_POSITION[(8, 1, 'E')] = (455-1, 199-35)
    POINT_POSITION[(8, 1, 'F')] = (552-1, 135-35)
    POINT_POSITION[(8, 1, 'G')] = (531-1, 458-35)
    POINT_POSITION[(8, 1, 'H')] = (594-1, 365-35)
    POINT_POSITION[(8, 1, 'I')] = (629-1, 243-35)
    POINT_POSITION[(8, 1, 'J')] = (754-1, 156-35)
    POINT_POSITION[(8, 1, 'K')] = (379-1, 470-35)
    POINT_POSITION[(8, 1, 'L')] = (787-1, 384-35)
    POINT_POSITION[(8, 2, 'A')] = (488-1, 432-35)
    POINT_POSITION[(8, 2, 'B')] = (496-1, 297-35)
    POINT_POSITION[(8, 2, 'C')] = (211-1, 259-35)
    POINT_POSITION[(8, 2, 'D')] = (660-1, 409-35)
    POINT_POSITION[(8, 2, 'E')] = (646-1, 296-35)
    POINT_POSITION[(8, 2, 'F')] = (375-1, 146-35)
    POINT_POSITION[(8, 2, 'G')] = (218-1, 109-35)
    POINT_POSITION[(8, 2, 'H')] = (810-1, 461-35)
    POINT_POSITION[(8, 2, 'I')] = (789-1, 343-35)
    POINT_POSITION[(8, 2, 'J')] = (571-1, 206-35)
    POINT_POSITION[(8, 2, 'K')] = (557-1, 109-35)
    POINT_POSITION[(8, 2, 'L')] = (721-1, 124-35)
    POINT_POSITION[(8, 2, 'M')] = (840-1, 177-35)
    POINT_POSITION[(8, 3, 'A')] = (803-1, 199-35)
    POINT_POSITION[(8, 3, 'B')] = (586-1, 349-35)
    POINT_POSITION[(8, 3, 'C')] = (676-1, 236-35)
    POINT_POSITION[(8, 3, 'D')] = (540-1, 124-35)
    POINT_POSITION[(8, 3, 'E')] = (473-1, 221-35)
    POINT_POSITION[(8, 3, 'F')] = (375-1, 401-35)
    POINT_POSITION[(8, 3, 'G')] = (390-1, 289-35)
    POINT_POSITION[(8, 3, 'H')] = (308-1, 207-35)
    POINT_POSITION[(8, 3, 'I')] = (174-1, 313-35)
    POINT_POSITION[(8, 3, 'J')] = (466-1, 484-35)
    POINT_POSITION[(8, 3, 'K')] = (287-1, 87-35)
    POINT_POSITION[(8, 3, 'L')] = (144-1, 168-35)
    POINT_POSITION[(8, 4, 'A')] = (683-1, 124-35)
    POINT_POSITION[(8, 4, 'B')] = (796-1, 289-35)
    POINT_POSITION[(8, 4, 'C')] = (496-1, 116-35)
    POINT_POSITION[(8, 4, 'D')] = (592-1, 296-35)
    POINT_POSITION[(8, 4, 'E')] = (774-1, 446-35)
    POINT_POSITION[(8, 4, 'F')] = (308-1, 101-35)
    POINT_POSITION[(8, 4, 'G')] = (278-1, 169-35)
    POINT_POSITION[(8, 4, 'H')] = (398-1, 267-35)
    POINT_POSITION[(8, 4, 'I')] = (444-1, 395-35)
    POINT_POSITION[(8, 4, 'J')] = (564-1, 484-35)
    POINT_POSITION[(8, 4, 'K')] = (339-1, 506-35)
    POINT_POSITION[(8, 4, 'L')] = (264-1, 386-35)
    POINT_POSITION[(8, 4, 'M')] = (127-1, 296-35)

    POINT_POSITION[(9, 1, 'A')] = relative_to_absolute((-0.22, -0.18))
    POINT_POSITION[(9, 1, 'B')] = relative_to_absolute((-0.272, -0.029))
    POINT_POSITION[(9, 1, 'C')] = relative_to_absolute((-0.361, 0.07))
    POINT_POSITION[(9, 1, 'D')] = relative_to_absolute((0.139, -0.158))
    POINT_POSITION[(9, 1, 'E')] = relative_to_absolute((-0.005, -0.1))
    POINT_POSITION[(9, 1, 'F')] = relative_to_absolute((-0.109, 0.052))
    POINT_POSITION[(9, 1, 'G')] = relative_to_absolute((-0.189, 0.154))
    POINT_POSITION[(9, 1, 'H')] = relative_to_absolute((-0.048, 0.242))
    POINT_POSITION[(9, 1, 'I')] = relative_to_absolute((-0.001, 0.186))
    POINT_POSITION[(9, 1, 'J')] = relative_to_absolute((0.062, 0.13))
    POINT_POSITION[(9, 1, 'K')] = relative_to_absolute((0.131, -0.064))
    POINT_POSITION[(9, 1, 'L')] = relative_to_absolute((0.296, -0.203))
    POINT_POSITION[(9, 1, 'M')] = relative_to_absolute((0.265, -0.04))
    POINT_POSITION[(9, 1, 'N')] = relative_to_absolute((0.406, 0.06))
    POINT_POSITION[(9, 1, 'O')] = relative_to_absolute((0.264, 0.157))


def load_all_data():
    load_point_positions()
    load_images()
    # load_decisive_data()
