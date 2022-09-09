import threading as th
import time

from airtest.core.api import start_app, text
from constants.custom_expections import (CriticalErr, ImageNotFoundErr,
                                         NetworkErr)
from constants.image_templates import (ChooseShipImages, ConfirmImage,
                                       FightImage, GameUI, RepairImage,
                                       StartImage, SymbolImage, ChapterImage)
from constants.keypoint_info import BLOODLIST_POSITION
from constants.load_data import load_all_data
from constants.other_constants import INFO2, INFO3
from controller.run_timer import (ClickImage, GetImagePosition, ImagesExist,
                             PixelChecker, Timer, WaitImage, WaitImages)
from utils.logger import logit

from game.get_game_info import (CheckSupportStatu, DetectShipStatu,
                                ExpeditionStatus)
from game.identify_pages import get_now_page, identify_page, wait_pages
from game.switch_page import (GoMainPage, goto_game_page, is_bad_network,
                              load_game_ui, process_bad_network)


@logit(level=INFO2)
def SL(timer: Timer):
    restart(timer)
    GoMainPage(timer)
    timer.set_page('main_page')

@logit(level=INFO2)
def start_march(timer:Timer):
    timer.Android.click(900, 500, 1, delay=0)  # 点击：开始出征
    start_time = time.time()
    while identify_page(timer, 'fight_prepare_page'):
        if(time.time() - start_time > 3):
            timer.Android.click( 900, 500, 1, delay=0)
        if ImagesExist(timer, SymbolImage[3], need_screen_shot=0):
            return "dock is full"
        if ImagesExist(timer, SymbolImage[9], need_screen_shot=0):
            return "out of times"
        if False:  # TODO: 大破出征确认
            pass
        if False:  # TODO: 补给为空
            pass
        if time.time() - start_time > 15:
            if process_bad_network(timer):
                if identify_page(timer, 'fight_prepare_page'):
                    return start_march(timer)
                else:
                    return 'failed'
            else:
                raise TimeoutError("map_fight prepare timeout")
    return "success"

@logit(level=INFO2)
def ConfirmOperation(timer: Timer, must_confirm=0, delay=0.5, confidence=.9, timeout=0):
    """等待并点击弹出在屏幕中央的各种确认按钮

    Args:
        must_confirm (int, optional): 是否必须按. Defaults to 0.
        delay (float, optional): 点击后延时(秒). Defaults to 0.5.
        timeout (int, optional): 等待延时(秒),负数或 0 不等待. Defaults to 0.

    Raises:
        ImageNotFoundErr: 如果 must_confirm = True 但是 timeout 之内没找到确认按钮排除该异常
    Returns:
        bool:True 为成功,False 为失败
    """
    pos = WaitImages(timer, ConfirmImage[1:], confidence, timeout=timeout)
    if pos is None:
        if (must_confirm == 1):
            raise ImageNotFoundErr("no confirm image found")
        else:
            return False
    res = GetImagePosition(timer, ConfirmImage[pos + 1], 0)
    timer.Android.click(res[0], res[1], delay=delay)
    return True


@logit(level=INFO3)
def log_in(timer: Timer, account, password):
    pass


@logit(level=INFO3)
def log_out(timer: Timer, account, password):
    """在登录界面登出账号

    Args:
        timer (Timer): _description_
        account (_type_): _description_
        password (_type_): _description_
    """


@logit(level=INFO3)
def start_game(timer: Timer, account=None, password=None, delay=1.0):
    """启动游戏(实现不优秀,需重写)

    Args:
        timer (Timer): _description_
        TryTimes (int, optional): _description_. Defaults to 0.

    Raises:
        NetworkErr: _description_
    """
    start_app("com.huanmeng.zhanjian2")
    res = WaitImages(timer, [StartImage[2]] + ConfirmImage[1:], 0.85, timeout=60 * delay)

    if res is None:
        raise TimeoutError("start_app timeout")
    if res != 0:
        ConfirmOperation(timer)
        if WaitImage(timer, StartImage[2], timeout=200) == False:
            raise TimeoutError("resource downloading timeout")
    if account != None and password != None:
        timer.Android.click(75, 450)
        if WaitImage(timer, StartImage[3]) == False:
            raise TimeoutError("can't enter account manage page")
        timer.Android.click(460, 380)
        if WaitImage(timer, StartImage[4]) == False:
            raise TimeoutError("can't logout successfully")
        timer.Android.click(540, 180)
        for _ in range(20):
            p = th.Thread(target=lambda: timer.Android.ShellCmd('input keyevent 67'))
            p.start()
        p.join()
        text(str(account))
        timer.Android.click(540, 260)
        for _ in range(20):
            p = th.Thread(target=lambda: timer.Android.ShellCmd('input keyevent 67'))
            p.start()
        p.join()
        time.sleep(0.5)
        text(str(password))
        timer.Android.click(400, 330)
        res = WaitImages(timer, [StartImage[5], StartImage[2]])
        if res is None:
            raise TimeoutError("login timeout")
        if res == 0:
            raise BaseException("password or account is wrong")
    while ImagesExist(timer, StartImage[2]):
        ClickImage(timer, StartImage[2])
    try:
        GoMainPage(timer)
    except:
        raise BaseException("fail to start game")


@logit(level=INFO3)
def restart(timer: Timer, times=0, *args, **kwargs):

    try:
        timer.Android.ShellCmd("am force-stop com.huanmeng.zhanjian2")
        timer.Android.ShellCmd("input keyevent 3")
        start_game(timer, **kwargs)
    except:
        if (timer.Windows.is_android_online() == False):
            pass

        elif (times == 1):
            raise CriticalErr("on restart,")

        elif (timer.Windows.CheckNetWork() == False):
            for i in range(11):
                time.sleep(10)
                if (timer.Windows.CheckNetWork() == True):
                    break
                if (i == 10):
                    raise NetworkErr()

        elif (timer.Android.is_game_running()):
            raise CriticalErr("CriticalErr on restart function")

        timer.Windows.ConnectAndroid()
        restart(timer, times + 1, *args, **kwargs)


@logit(level=INFO3)
def expedition(timer: Timer, force=False):
    """检查远征,如果有未收获远征,则全部收获并用原队伍继续

    Args:
        force (bool): 是否强制检查
    """
    timer.expedition_status.update(force=force)
    while (timer.expedition_status.is_ready()):
        # try:
        goto_game_page(timer, 'expedition_page')
        pos = WaitImage(timer, GameUI[6], timeout=2)
        # TODO: 暂时修复远征按钮的位置，需要更好的解决方案
        if pos:
            timer.Android.click(pos[0], pos[1], delay=1)
            WaitImage(timer, FightImage[3], after_get_delay=.25)
            timer.Android.click(900, 500, delay=1)
            ConfirmOperation(timer, must_confirm=1, delay=.5, confidence=.9)
            timer.expedition_status.update()
        else:
            break



@logit(level=INFO3)
def DestoryShip(timer, reserve=1, amount=1):
    # amount:重要舰船的个数
    # 解装舰船
    goto_game_page(timer, 'destroy_page')

    WaitImage(timer, SymbolImage[5], after_get_delay=.33)
    timer.Android.click(301, 25)  # 这里动态延迟，点解装
    WaitImage(timer, SymbolImage[6], after_get_delay=.33)
    timer.Android.click(90, 206)  # 点添加
    WaitImage(timer, SymbolImage[7], after_get_delay=.33)
    # TODO：有bug，先注释 # 进去
    # timer.Android.click(877, 378, delay=1)

    # timer.Android.click(544, 105, delay=0.33)
    # timer.Android.click(619, 105, delay=0.33)
    # timer.Android.click(624, 152, delay=0.33)
    # timer.Android.click(537, 204, delay=0.33)
    # timer.Android.click(851, 459, delay=0.33)
    # 筛出第一波

    for i in range(1, 8):
        timer.Android.click(i * 100, 166, delay=0.33)
        timer.Android.click(i * 100, 366, delay=0.33)
    # 选中第一波

    timer.Android.click(860, 480, delay=1)

    if (ImagesExist(timer, GameUI[8])):
        timer.Android.click(807, 346)
    timer.Android.click(870, 480, delay=1)
    timer.Android.click(364, 304, delay=0.66)  # TODO：需要容错，如果没有选中任何船咋办？
    """# 清理第一波

    # TODO：跟上面一样
    # timer.Android.click(90, 206, delay=1)
    # WaitImage(timer, SymbolImage[7], after_get_delay=.5)
    # timer.Android.click(877, 378, delay=1)  # 点“类型”
    # timer.Android.click(536, 62, delay=0.33)
    # timer.Android.click(851, 459, delay=0.33)
    # # 再进去并筛出第二波
    # if(reserve == 1):
    #     timer.Android.click(853, 270, delay=0.66)
    #     timer.Android.click(579, 208, delay=0.66)
    # # 是否解装小船
    # for i in range(1, amount + 1):
    #     timer.Android.click(i * 100, 166, delay=0.33)
    # # 选中第二波

    # timer.Android.click(860, 480, delay=0.66)
    # timer.Android.click(870, 480, delay=1)
    # if(ImagesExist(timer, GameUI[8])):
    #     click(807, 346)"""


@logit(level=INFO2)
def verify_team(timer: Timer):
    """检验目前是哪一个队伍(1~4)
    含网络状况处理
    Args:
        timer (Timer): _description_

    Raises:
        ImageNotFoundErr: 未找到队伍标志
        ImageNotFoundErr: 不在相关界面

    Returns:
        int: 队伍编号(1~4)
    """
    if (identify_page(timer, 'fight_prepare_page') == False):
        raise ImageNotFoundErr("not on fight_prepare_page")
    
    for _ in range(5):
        for i, position in enumerate([(64, 83), (186, 83), (310, 83), (430, 83)]):
            # if(S.DEBUG):print(timer.screen[83][64])
            if(PixelChecker(timer, position, bgr_color=(228, 132, 16))):
                return i + 1
        timer.UpdateScreen()
        
        
    if(process_bad_network(timer)):
        return verify_team(timer)
    
    timer.log_screen()
    raise ImageNotFoundErr()


@logit(level=INFO2)
def MoveTeam(timer: Timer, target, try_times=0):
    """切换队伍
    Args:
        timer (Timer): _description_
        target (_type_): 目标队伍
        try_times: 尝试次数
    Raise:
        ValueError: 切换失败
        ImageNotFoundErr: 不在相关界面
    """
    if (try_times > 3):
        raise ValueError("can't change team sucessfully")

    if(identify_page(timer, 'fight_prepare_page') == False):
        timer.log_screen()
        raise ImageNotFoundErr("not on 'fight_prepare_page' ")

    if (verify_team(timer) == target):
        return
    print("正在切换队伍到:", target)
    timer.Android.click(110 * target, 81)
    if (verify_team(timer) != target):
        MoveTeam(timer, target, try_times + 1)


@logit(level=INFO3)
def SetSupport(timer: Timer, target, try_times=0):
    """启用战役支援

    Args:
        timer (Timer): _description_
        target (bool, int): 目标状态
    Raise:
        ValueError: 未能成功切换战役支援状态
    """
    target = bool(target)
    goto_game_page(timer, "fight_prepare_page")
    # if(bool(PixelChecker(timer, (623, 75), )) == ):
    #
    # 支援次数已用尽
    if (CheckSupportStatu(timer) != target):
        timer.Android.click(628, 82, delay=1)
        timer.Android.click(760, 273, delay=1)
        timer.Android.click(480, 270, delay=1)

    if (is_bad_network(timer, 0) or CheckSupportStatu(timer) != target):
        if (process_bad_network(timer, 'set_support')):
            SetSupport(timer, target)
        else:
            raise ValueError("can't set right support")


@logit(level=INFO3)
def QuickRepair(timer: Timer, repair_mode=2, *args, **kwargs):
    """战斗界面的快速修理

    Args:
        timer (Timer): _description_
        repair_mode:
            1: 快修，修中破
            2: 快修，修大破
    """
    ShipStatus = DetectShipStatu(timer)
    assert type(repair_mode) in [int, list]
    if type(repair_mode) == int:  # 指定所有统一修理方案
        repair_mode = [repair_mode for _ in range(6)]

    assert len(repair_mode) == 6
    need_repair = [False for _ in range(6)]
    for i, x in enumerate(repair_mode):
        assert x in [1, 2]
        if x == 1:
            need_repair[i] = ShipStatus[i+1] not in [-1, 0]
        elif x == 2:
            need_repair[i] = ShipStatus[i+1] not in [-1, 0, 1]

    print("ShipStatus:", ShipStatus)
    if any(need_repair) or ImagesExist(timer, RepairImage[1]):
        timer.Android.click(420, 420, delay=1.5)   # 进入修理页面
        # 快修已经开始泡澡的船
        pos = GetImagePosition(timer, RepairImage[1])
        while (pos != None):
            timer.Android.click(pos[0], pos[1], delay=1)
            pos = GetImagePosition(timer, RepairImage[1])
        # 按逻辑修理
        for i in range(1, 7):
            if need_repair[i-1]:
                timer.log_info("WorkInfo:" + str(kwargs))
                timer.log_info(str(i)+" Repaired")
                timer.Android.click(BLOODLIST_POSITION[0][i][0], BLOODLIST_POSITION[0][i][1], delay=1.5)
        # timer.Android.click(163, 420, delay=1) # 回到第一界面，并不需要，可直接出征


@logit(level=INFO3)
def GainBounds(timer: Timer):
    """检查任务情况,如果可以领取奖励则领取

    Args:
        timer (Timer): _description_
    """
    goto_game_page(timer, 'main_page')
    if not bool(PixelChecker(timer, (694, 457), bgr_color=(45, 89, 255))):
        return 'no'
    goto_game_page(timer, 'mission_page')
    goto_game_page(timer, 'mission_page')
    if ClickImage(timer, GameUI[15]):
        ConfirmOperation(timer, must_confirm=1)
        return 'ok'
    elif ClickImage(timer, GameUI[12]):
        ConfirmOperation(timer, must_confirm=1)
        return 'ok'
    return 'no'
    #timer.Android.click(774, 502)


@logit(level=INFO2)
def RepairByBath(timer: Timer):
    """使用浴室修理修理时间最长的单位

    Args:
        timer (Timer): _description_
    """
    goto_game_page(timer, 'choose_repair_page')
    timer.Android.click(115, 233)
    if (not identify_page(timer, 'choose_repair_page')):
        if (identify_page(timer, 'bath_page')):
            timer.set_page('bath_page')
        else:
            timer.set_page(get_now_page(timer))


@logit(level=INFO2)
def SetAutoSupply(timer: Timer, type=1):
    timer.UpdateScreen()
    NowType = int(PixelChecker(timer, (48, 508), (224, 135, 35)))
    if (NowType != type):
        timer.Android.click(44, 503, delay=0.33)


@logit(level=INFO2)
def Supply(timer: Timer, List=[1, 2, 3, 4, 5, 6], try_times=0):
    """补给指定舰船

    Args:
        timer (Timer): _description_
        List (list, optional): 补给舰船列表,可以为单个整数. Defaults to [1, 2, 3, 4, 5, 6].
        try_times (int, optional): _description_. Defaults to 0.

    Raises:
        ValueError: 补给失败
        TypeError: List 参数有误
    """
    if (try_times > 3):
        raise ValueError("can't supply ship")

    if (isinstance(List, int)):
        List = [List]

    timer.Android.click(293, 420)
    for x in List:
        if not isinstance(x, int):
            raise TypeError("ship must be represent as a int but get" + str(List))
        timer.Android.click(110 * x, 241)

    if (is_bad_network(timer, 0)):
        process_bad_network(timer, 'supply ships')
        Supply(timer, List, try_times + 1)


@logit(level=INFO2)
def ChangeShip(timer: Timer, team, pos=None, name=None, pre=None, detect_ship_statu=True):
    """切换舰船(不支持第一舰队)

    """
    if (team is not None):
        goto_game_page(timer, 'fight_prepare_page')
        MoveTeam(timer, team)
        if (team >= 5):
            # 切换为预设编队
            # 暂不支持
            return

    # 切换单船
    # 懒得做 OCR 所以默认第一个
    if (detect_ship_statu):
        DetectShipStatu(timer)
    if name is None and timer.ship_status[pos] == -1:
        return
    timer.Android.click(110 * pos, 250, delay=0)
    res = WaitImages(timer, [ChooseShipImages[1], ChooseShipImages[2]], after_get_delay=.4, gap=0)
    if (res == 1):
        timer.Android.click(839, 113)

    if name is None:
        timer.Android.click(83, 167, delay=0)
        wait_pages(timer, 'fight_prepare_page', gap=0)
        return

    timer.Android.click(700, 30, delay=0)
    WaitImage(timer, ChooseShipImages[3], gap=0, after_get_delay=.1)

    text(name)
    timer.Android.click(50, 50, delay=.5)
    if (timer.ship_status[pos] == -1):
        timer.Android.click(83, 167, delay=0)
    else:
        timer.Android.click(183, 167, delay=0)

    wait_pages(timer, 'fight_prepare_page', gap=0)


@logit(level=INFO3)
def ChangeShips(timer: Timer, team, list):
    """更换编队舰船

    Args:
        team (int): 2~4,表示舰队编号
        list (舰船名称列表): 

    For instance:
        ChangeShips(timer, 2, [None, "萤火虫", "伏尔塔", "吹雪", "明斯克", None, None])

    """
    if (team is not None):
        goto_game_page(timer, 'fight_prepare_page')
        MoveTeam(timer, team)

    DetectShipStatu(timer)
    for i in range(1, 7):
        if (timer.ship_status[i] != -1):
            ChangeShip(timer, team, 1, None, detect_ship_statu=False)
    list = list + [None] * 6
    time.sleep(.3)
    DetectShipStatu(timer)
    for i in range(1, 7):
        ChangeShip(timer, team, i, list[i], detect_ship_statu=False)


def get_new_things(timer: Timer, lock=0):
    pass


