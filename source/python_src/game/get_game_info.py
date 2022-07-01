
from api import *
from supports import *
from save_load import *
from game.switch_page import *
# 获取游戏信息

__all__ = ["GetChapter", "GetNode", "GetEnemyCondition", "DetectShipStatu", "DetectShipType",
           "UpdateShipPosition", "UpdateShipPoint", "CheckSupportStatu", "is_bad_network",
           "ExpeditionStatus", 'get_exercise_status', 'FightResult'
           ]


class ExpeditionStatus():
    def __init__(self, timer: Timer):
        self.exist_ready = False
        self.timer = timer

    def is_ready(self):
        self.update()
        return self.exist_ready

    def update(self):
        UpdateScreen(self.timer)
        if self.timer.now_page.name in ['expedition_page', 'map_page']:
            self.exist_ready = bool(PixelChecker(self.timer, (464, 11), bgr_color=(45, 89, 255)))
            return
        walk_to(self.timer, end='main_page')
        self.exist_ready = bool(PixelChecker(self.timer, (933, 454), bgr_color=(45, 89, 255)))


class FightResult():
    def __init__(self, timer: Timer):
        self.timer = timer
        self.result = 'D'
        self.mvp = 0
        self.experiences = [None, 0, 0, 0, 0, 0, 0]

    def detect_result(self):
        mvp_pos = GetImagePosition(self.timer, FightImage[14])
        self.mvp = get_nearest((mvp_pos[0], mvp_pos[1] + 20), BLOODLIST_POSITION[1])
        self.result = WaitImages(self.timer, fight_result_images)

    def detect_experiences(self):
        pass

    def __str__(self):
        return


@logit(level=INFO2)
def GetChapter(timer: Timer):
    """在出征界面获取当前章节(远征界面也可获取)

    Raises:
        TimeoutError: 无法获取当前章节

    Returns:
        int: 当前章节
    """
    for try_times in range(5):
        time.sleep(0.15 * 2 ** try_times)
        UpdateScreen(timer)
        for i in range(1, 9):
            if(ImagesExist(timer, ChapterImage[i], 0)):
                return i
    raise TimeoutError("can't vertify chapter")


@logit(level=INFO2)
def GetNode(timer: Timer):
    """不够完善"""
    """出征界面获取当前显示地图节点编号
    例如在出征界面显示的地图 2-5,则返回 5
    
    Returns:
        int: 节点编号
    """
    UpdateScreen(timer)
    for try_times in range(5):
        time.sleep(0.5 * 2 ** try_times)
        for i in range(1, 7):
            if(ImagesExist(timer, NumberImage[i], 0, confidence=0.95)):
                return i
    raise TimeoutError("can't vertify map")


@logit(level=INFO2)
def GetEnemyCondition(timer: Timer, type='exercise', *args, **kwargs):
    """获取敌方舰船类型数据并更新到 timer.enemy_type_count
    timer.enemy_type_count 为一个记录了敌方情况的字典
    使用了一个 C++ 写的识别程序叫 source.exe 在 .\\Data\\Tunnel\\ 下
    具体实现不介绍,当黑箱使用

    Args:
        type (str, optional): 描述情景. Defaults to 'exercise'.
            values:
                'exercise': 演习点击挑战后的一横排舰船
                'fight': 索敌成功后的两列三行
    """
    timer.enemy_type_count = {CV: 0, BB: 0, SS: 0, BC: 0, NAP: 0, DD: 0, ASDG: 0, AADG: 0,
                              CL: 0, CA: 0, CLT: 0, CVL: 0, NO: 0, AV: 0, "all": 0, CAV: 0, AV: 0,
                              BM: 0, SAP: 0, BG: 0, CBG: 0, SC: 0, BBV: 0, 'AP': 0}
    if(type == 'exercise'):
        type = 0
    if(type == 'fight'):
        type = 1

    if(ImagesExist(timer, FightImage[12])):
        # 特殊补给舰
        timer.enemy_type_count[SAP] = 1

    PIM.fromarray(timer.screen).convert("L").resize((960, 540)).save(".\\Data\\Tmp\\screen.PNG")
    img = PIM.open(".\\Data\\Tmp\\screen.PNG")
    input_path = os.path.join(S.TUNNEL_PATH, "args.in")
    output_path = os.path.join(S.TUNNEL_PATH, "res.out")

    delete_file(input_path)
    delete_file(output_path)
    args = "recognize\n6\n"

    for i, area in enumerate(TYPE_SCAN_AREA[type]):
        arr = np.array(img.crop(area))
        save_image(os.path.join(S.TUNNEL_PATH, str(i) + ".PNG"), arr, True)
        args += matri_to_str(arr)

    write_file(input_path, args)

    os.chdir(S.TUNNEL_PATH)
    os.system(".\Source.exe")
    os.chdir("..\\..\\")

    res = read_file(S.WORK_PATH + "Data\\Tunnel\\res.out").split()
    timer.enemy_type_count["ALL"] = 0
    for i, x in enumerate(res):
        timer.enemy_ship_type[i] = x
        timer.enemy_type_count[x] += 1
        timer.enemy_ship_type[i] = x
        if(x != NO):
            timer.enemy_type_count["ALL"] += 1

    timer.enemy_type_count[NAP] -= timer.enemy_type_count['AP'] - timer.enemy_type_count[SAP]

    if(S.DEBUG):
        for key, value in timer.enemy_type_count.items():
            if(value != 0 and key != 'AP'):
                print(key, ':', value, end=',')
        print("")


@logit(level=INFO2)
def DetectShipStatu(timer: Timer, type='prepare'):
    """检查我方舰船的血量状况(精确到红血黄血绿血)并更新到 timer.ship_status

    timer.ship_status:一个表示舰船血量状态的列表,从 1 开始编号.

        For Example:
        [-1, 0, 0, 1, 1, 2, 2] 表示 1,2 号位绿血,3,4 号位中破,5,6 号位大破

        values:
            -1:不存在该舰船
            0:绿血
            1:中破
            2:大破

    Args:
        type (str, optional): 描述在哪个界面检查. Defaults to 'prepare'.
            values:
                'prepare': 战斗准备界面
                'sumup': 单场战斗结算界面

    """

    """ToDo:
    血量检测精确到是否满血和是否触发中破保护
    血量检测精确到数值,相对误差少于 3%
    """

    UpdateScreen(timer)
    result = [-1, 0, 0, 0, 0, 0, 0]
    if(type == 'prepare'):
        for i in range(1, 7):
            pixel = timer.get_pixel(*BLOODLIST_POSITION[0][i])
            result[i] = CheckColor(pixel, BLOOD_COLORS[0])
            if(result[i] == 3 or result[i] == 2):
                result[i] = 2
            elif(result[i] == 0):
                result[i] = 0
            elif(result[i] == 4):
                result[i] = -1
            else:
                result[i] = 1

    if(type == 'sumup'):
        for i in range(1, 7):
            if(timer.ship_status[i] == -1):
                result[i] = -1
                continue
            pixel = timer.get_pixel(*BLOODLIST_POSITION[1][i])
            result[i] = CheckColor(pixel, BLOOD_COLORS[1])
    timer.ship_status = result
    if(S.DEBUG):
        print(type, ":ship_status =", result)
    return result

@logit(level=INFO2)
def DetectShipType(timer: Timer):
    """ToDo
    在出征准备界面读取我方所有舰船类型并返回该列表
    """

@logit(level=INFO2)
def UpdateShipPosition(timer: Timer):
    """在战斗移动界面(有一个黄色小船在地图上跑)更新黄色小船的位置

    Args:
        timer (Timer): 记录器
    """
    pos = GetImagePosition(timer, FightImage[7], 0, 0.8)
    if(pos == None):
        pos = GetImagePosition(timer, FightImage[8], 0, 0.8)
    if(pos == None):
        return

    timer.ship_position = pos


def UpdateShipPoint(timer: Timer):
    timer.update_ship_point()


def get_exercise_status(timer: Timer):
    """检查演习界面,第 position 个位置,是否为可挑战状态,强制要求屏幕中只有四个目标

    Args:
        position (_type_): 编号从屏幕中的位置编起,如果滑动显示了第 2-5 个敌人,那么第二个敌人编号为 1

    Returns:
        bool: 如果可挑战,返回 True ,否则为 False,1-based
    """
    swipe(timer, 800, 200, 800, 400)
    UpdateScreen(timer)
    result = [None, ]
    for position in range(1, 5):
        result.append(bool(math.sqrt(CalcDis(timer.get_pixel(770, position * 110 - 10), CHALLENGE_BLUE)) <= 50))
    swipe(timer, 800, 400, 800, 200)
    UpdateScreen(timer)
    result.append(bool(math.sqrt(CalcDis(timer.get_pixel(770, 4 * 110 - 10), CHALLENGE_BLUE)) <= 50))
    swipe(timer, 800, 200, 800, 400)
    return result


def CheckSupportStatu(timer: Timer):
    """在出征准备界面检查是否开启了战役支援(有开始出征按钮的界面)

    Returns:
        bool: 如果开启了返回 True,否则返回 False
    """
    UpdateScreen(timer)
    pixel = timer.get_pixel(75, 623)
    d1 = CalcDis(pixel, SUPPORT_ENALBE)
    d2 = CalcDis(pixel, SUPPOER_DISABLE)
    return d1 < d2
