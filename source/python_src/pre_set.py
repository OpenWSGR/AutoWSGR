
from fight import *
from game import *
from supports import *


def weekliy(timer, team=4):
    week123(timer)
    RepairByBath(timer)
    RepairByBath(timer)

    week4(timer)
    week5(timer, team, change=0)
    week6(timer, team, change=0)
    week7(timer, team, change=0)
    week8(timer, team, change=0)


def week123(timer, team=4):
    ChangeShips(timer, team, [None, "萤火虫", "伏尔塔", "吹雪", "明斯克"])
    work(timer, lambda: normal_fight(timer, 1, 5, team), 3)
    work(timer, lambda: normal_fight(timer, 1, 1, team), 2, end=True)
    GainBounds(timer)
    work(timer, lambda: normal_fight(timer, 2, 1, team, mod=2), 5, end=True)
    ChangeShip(timer, team, 5, "基辅")
    ChangeShip(timer, team, 6, "黑潮")
    GainBounds(timer)
    work(timer, lambda: normal_fight(timer, 3, 2, team, mod=1), 5, end=True)
    GainBounds(timer)


def week4(timer, team=4, times=5, change=1):
    if (change):
        ChangeShips(timer, team, [None, "U-1405", "鲃鱼", "大青花鱼", "狼群47", "U-1206", "射水鱼"])
    work(timer, lambda: normal_fight(timer, 4, 4, team, mod=1), times, end=1)
    GainBounds(timer)


def week5(timer, team=4, times=5, change=1):
    if (change):
        ChangeShips(timer, team, [None, "U-1405", "鲃鱼", "大青花鱼", "狼群47", "U-1206", "射水鱼"])
    work(timer, lambda: normal_fight(timer, 5, 5, team, mod=1), times, end=1)
    GainBounds(timer)


def week6(timer, team=4, times=5, change=1):
    if (change):
        ChangeShips(timer, team, [None, "U-1405", "鲃鱼", "大青花鱼", "狼群47", "U-1206", "射水鱼"])
    work(timer, lambda: normal_fight(timer, 6, 3, team, mod=1), times, end=1)
    GainBounds(timer)


def week7(timer, team=4, times=5, change=1):
    if (change):
        ChangeShips(timer, team, [None, "U-1405", "鲃鱼", "大青花鱼", "狼群47", "U-1206", "射水鱼"])
    work(timer, lambda: normal_fight(timer, 7, 4, team, mod=2), times, end=1)
    GainBounds(timer)


def week8(timer, team=4, times=5, change=1):
    if (change):
        ChangeShips(timer, team, [None, "U-1405", "鲃鱼", "大青花鱼", "狼群47", "U-1206", "射水鱼"])
    work(timer, lambda: normal_fight(timer, 8, 4, team, mod=1), times, end=1)
    GainBounds(timer)


def Wait(timer: Timer, all_time=10**6, repair=True):
    """等待并监控
    Args:
        timer (Timer): _description_
        all_time (int, optional): 等待时间. Defaults to 10**6.
        repair (bool, optional):  等待中是否进行修理操作. Defaults to True.
    """
    last_repair_time = time.time()
    goto_game_page(timer, 'main_page')
    expedition(timer)
    RepairByBath(timer)
    goto_game_page(timer, 'main_page')
    for _ in range(int(all_time / 10)):
        print("Waiting Round")
        if time.time() - last_repair_time > 1200:
            RepairByBath(timer)
            goto_game_page(timer, 'main_page')
            last_repair_time = time.time()
        expedition(timer)
        goto_game_page(timer, 'main_page')
        time.sleep(10)
