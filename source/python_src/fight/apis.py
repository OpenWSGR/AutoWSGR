from tkinter import E
from game import *
from supports import *
from api import *
from fight.data_structures import *

__all__ = ['fight', 'normal_fight', 'choose_decision', 'work', 'SL']

def work(timer:Timer, fun, times=1, end=False):
    while(times):
        print("Round", times)
        try:
            res = fun()
            if(res == 'retry'):
                continue
            if(res is not None):
                print(res)
                time.sleep(1)
            if(end and timer.is_fight_end() == False):
                print("The Fight isn't end, retrying")
                continue
            
        except (BaseException, Exception) as e:
            print(e)
            # TODO: 有bug，模拟器闪退
            if(time.time() - timer.last_error_time < 2000 or is_android_online(timer, 5) == False):
                RestartAndroid(timer)
                ConnectAndroid(timer)
                start_game(timer)
            else:
                if(is_game_running(timer)):
                    if(wait_network() == False):
                        raise NetworkErr("Network error, please check your hardware or network configuration")
                    if(process_bad_network(timer)):
                        if(get_now_page(timer) is not None):
                            goto_game_page(timer, 'main_page')
                        else:
                            restart(timer)
                    else:
                        restart(timer)
                else:
                    restart(timer)
                    
        times -= 1

@logit(level=INFO3)
def normal_fight(timer: Timer, chapter, node, team, decision_maker: DecisionBlock = None, repair: RepairBlock = None, *args, **kwargs):
    """进行常规地图战斗

    Args:
        timer (Timer): _description_
        chapter (int): 章节
        node (int): 节点
        team (int): 1~4 的整数
        decision_maker (DecisionBlock): 决策模块. Defaults to None.
        repair (RepairBlock, optional): 修理模块. Defaults to None.
        kwargs: 一些其它参数
    Returns:
        'dock is full':船坞已满
        'SL': 进行了 SL 操作
    """
    if(decision_maker is None):
        decision_maker = timer.defaul_decision_maker
    timer.oil = timer.ammo = 10
    # TODO: 并无耦合的意义，先注释掉
    # goto_game_page(timer, 'map_page')
    # expedition(timer)
    goto_game_page(timer, 'map_page')
    change_fight_map(timer, chapter, node)
    goto_game_page(timer, 'fight_prepare_page')
    MoveTeam(timer, team)
    QuickRepair(timer, repair)
    click(timer, 900, 500, 1, delay=0)
    start_time = time.time()
    while(identify_page(timer, 'fight_prepare_page')):
        UpdateScreen(timer)
        if(ImagesExist(timer, SymbolImage[3], need_screen_shot=0)):
            return "dock is full"
        if(False):
            """大破出征确认
            """
        if(False):
            """补给为空
            """
            return 'supply is empty'
        if(time.time() - start_time > 15):
            if(process_bad_network(timer)):
                if(identify_page(timer, 'fight_prepare_page')):
                    return normal_fight(timer, chapter, node, team, decision_maker, repair, *args, **kwargs)
                else:
                    pass
            else:
                raise TimeoutError("map_fight prepare timeout")

    return map_fight(timer, decision_maker, 'normal', 'map_page', *args, **kwargs)

@logit(level=INFO2)
def fight_during(timer: Timer, decision_maker: DecisionBlock = None, *args, **kwargs):
    """单点战斗,完成选阵型后的所有操作,到战斗结束进入结算界面为止

    Raise:
        TimeoutError:未知原因导致无法进行操作
    """
    if decision_maker is None:
        decision_maker = timer.defaul_decision_maker

    res = WaitImages(timer, [FightImage[3], FightImage[6]], timeout=120)
    if(res == 0):
        return
    if res is None:
        if(process_bad_network(timer)):
            fight_during(timer, decision_maker, *args, **kwargs)
        else:
            raise TimeoutError("unknown error lead to fight timeout")

    night = decision_maker.make_decision(timer, type='night', *args, **kwargs)
    choose_decision(timer, 'night', night, *args, **kwargs)

    if(night == 0):
        return

    res = WaitImage(timer, FightImage[3], timeout=60)

    if(res == False):
        if(process_bad_network(timer)):
            fight_during(timer, decision_maker, *args, **kwargs)
        else:
            raise TimeoutError("unknown error lead to fight timeout")

@logit(level=INFO2)
def fight_end(timer: Timer, type='map_fight', end_page=None, gap=.15, begin=True, try_times=0, *args, **kwargs):
    """战斗结算,到领取舰船结束(可能没有)为止
    Todo:
        锁定获取的新船

    Args:
        timer (Timer): _description_
        type (str, optional): 战斗类型. Defaults to 'fight'.
        end_page (_type_, optional): 结束后应该回到哪个界面. Defaults to None.
        gap (float, optional): 处理等待. Defaults to .15.
        begin (bool, optional): 是否仍处于战果界面. Defaults to True.

    Returns:
       'map_end':地图已经结束
       'proceed':需要继续决策
       'fight_end':单点战斗已经结束
    Rasie:
        TimeoutError:未知原因导致了战斗无法结算
    """
    if(try_times > 30):
        if(process_bad_network(timer)):
            try_times = 0
        else:
            raise TimeoutError("unknown error lead to fight_end timeout")

    if(type == 'map_fight'):
        kwargs['oil_check'] = True
    if type in ['exercise', 'battle']:
        kwargs['no_ship_get'] = True
        kwargs['no_flagship_check'] = True
        kwargs['no_proceed'] = True

    time.sleep(gap)
    if(begin):
        """点击继续部分
        """
        time.sleep(1.5)
        DetectShipStatu(timer, 'sumup')
        timer.fight_result.detect_result()
        print(timer.fight_result)
        click(timer, 900, 500, 2, .16)
        if('no_ship_get' not in kwargs and ImagesExist(timer, SymbolImage[8], need_screen_shot=0)):
            click(timer, 900, 500, 1, .25)

    if(type != 'map_fight'):
        time.sleep(1)
        return 'fight_end'

    UpdateScreen(timer)
    if(end_page is not None and identify_page(timer, end_page, 0)):
        return 'map_end'
    if('no_flagship_check' not in kwargs and ImagesExist(timer, FightImage[4], need_screen_shot=0)):
        """旗舰大破"""
        ClickImage(timer, FightImage[4], must_click=True, delay=.25)
        return 'map_end'
    if('no_ship_get' not in kwargs and ImagesExist(timer, SymbolImage[8], need_screen_shot=0)):
        click(timer, 900, 500, 1, .25)
    if('no_proceed' not in kwargs and ImagesExist(timer, FightImage[5], need_screen_shot=0)):
        return 'proceed'
    if('oil_check' in kwargs):
        # 检查燃油
        pass

    return fight_end(timer, type, end_page, gap, False, try_times + 1, *args, **kwargs)

@logit(level=INFO2)
def wait_until_decision(timer: Timer, type='map_fight', *args, **kwargs):
    """一轮战斗,等待到需要某一决策时

    Args:
        timer (Timer): _description_S
        type (str, optional): 战斗类型. Defaults to 'map_fight'.
            values:
                'map_fight':地图上的战斗
                'single_fight':遭遇战等战斗
                'exercise':演习
                'battle':战役

    Raises:
        TimeoutError: 无法完成该操作

    Returns:
        'fight':是否战斗(撤退或迂回或战斗)
        'formation':何种阵型
        'fight_start':已经开始战斗
        'fight_condition':选择战况

    """

    if(type == 'fight'):
        kwargs['no_confirm'] = True
        kwargs['no_fight_condition'] = True
        kwargs['no_yellow_ship'] = True
        kwargs['no_get_enemy'] = True

    if type in ['exercise', 'battle']:
        kwargs['no_confirm'] = True
        kwargs['no_fight_condition'] = True
        kwargs['no_yellow_ship'] = True
        kwargs['no_get_enemy'] = True

    fun_start_time = time.time()

    for i in range(1, 1000):
        if(i % 5 == 0):
            print("WaitRound")

        if 'no_click' not in kwargs and i % 2 == 1:
            p = click(timer, 380, 520, delay=0, enable_subprocess=True, print=0, no_log=True)

        UpdateScreen(timer)

        if "no_yellow_ship" not in kwargs:
            UpdateShipPosition(timer)
            UpdateShipPoint(timer)
        if "no_confirm" not in kwargs:
            ConfirmOperation(timer, delay=0)
        if "no_fight_condition" not in kwargs and ImagesExist(timer, FightImage[10], 0):
            return 'fight_condition'

        if ImagesExist(timer, FightImage[2], confidence=0.8, need_screen_shot=0) or "rec_must_success" not in kwargs and ImagesExist(timer, FightImage[1], 0, 0.8) or "ship_enough" not in kwargs and ImagesExist(timer, SymbolImage[4], 0, 0.8):

            if (ImagesExist(timer, FightImage[2], 0)):
                if 'no_get_enemy' not in kwargs:
                    GetEnemyCondition(timer, 'fight')
                return 'fight'

            elif(ImagesExist(timer, FightImage[1], 0, confidence=.8)):
                timer.enemy_type_count['ALL'] = -1
                return 'formation'

            return 'fight_start'

        if 'no_click' not in kwargs and i % 2 == 1:
            p.join()

        if(time.time() - fun_start_time > 15):
            break

    if(process_bad_network(timer)):
        return wait_until_decision(timer, type, *args, **kwargs)

    raise TimeoutError('unknown error')

@logit(level=INFO2)
def choose_decision(timer: Timer, type, value=1, extra_check=False, try_times=0, *args, **kwargs):
    """执行战斗种做出的决策

    Args:
        type (_type_): 决策种类
            values:
                'fight':是否进行战斗
                'figth_condition':选择战况
                'formation':选择战斗阵型
                'proceed': 是否继续前进或回港
        value (int, optional): 决策参数. Defaults to 1.
            values:
                0:撤退 if type=='fight'
                1:战斗 if type=='fight'
                2:迂回 if type=='fight'

        kwargs: 一些其它参数
    Returns:
        'SL': 进行了 SL 操作
        True:迂回成功
        Fakse:迂回失败
    Raise:
        ImageNorFoundErr:当前不存在该操作
        TimeoutError:不能完成该操作
    """
    if(try_times > 3):
        raise TimeoutError("can't do this operaion")

    try:
        if(type == 'fight'):
            if(extra_check and not ImagesExist(timer, FightImage[2])):
                raise ImageNotFoundErr("no fight choose options")

            if(value == 1):
                click(timer, 855, 501, delay=0)
                res = WaitImages(timer, [FightImage[1], SymbolImage[4]], .8)
                if(res == None):
                    raise BaseException()
                print("decision done:", type, value)

            elif(value == 0):
                click(timer, 677, 492, delay=0)
                print("decision done:", type, value)
                return

            elif(value == 2):
                if(not ImagesExist(timer, FightImage[13])):
                    raise ImageNotFoundErr("no detour option")

                click(timer, 540, 500, delay=0)
                res = WaitImages(timer, [FightImage[1], FightImage[7], FightImage[8]], gap=0)
                if(res == 0):
                    return False
                elif(res == 1 or res == 2):
                    print("decision done:", type, value)
                    return True
                else:
                    raise BaseException

        if(type == 'formation'):
            if(extra_check and not ImagesExist(timer, FightImage[1], 0, .8)):
                raise ImageNotFoundErr("no formation choose options")
            if(value == 0):
                SL(timer)
                print("decision done:", type, 'SL')
                return 'SL'

            click(timer, 573, value * 100 - 20, delay=2)
            res = WaitImage(timer, SymbolImage[4])
            if(res == False):
                raise BaseException()
            print("decision done:", type, value)

        if(type == 'night'):
            if(not bool(value)):
                click(timer, 615, 350, delay=2)
                if(WaitImage(timer, FightImage[3], confidence=0.85) == False):
                    raise BaseException()
                print("decision done:", type, value)
            else:
                click(timer, 325, 350, delay=2)
                if(WaitImage(timer, FightImage[6], 0, .8) == False):
                    raise BaseException()
            print("decision done:", type, value)

        if(type == 'proceed'):
            if(not bool(value)):
                # TODO：回港需要结束战斗
                click(timer, 615, 350)
            else:
                click(timer, 325, 350)

        if(type == 'fight_condition'):
            if(ImagesExist(timer, FightImage[10])):
                click(timer, *FIGHT_CONDITIONS_POSITON[value])
            else:
                raise ImageNotFoundErr("no fight condition options")

    except:
        print("can't do this opeation,checking")
        if(process_bad_network(timer)):
            return choose_decision(timer, type, value, extra_check, try_times + 1)
        else:
            raise TimeoutError("can't do this operation" + type + str(value))

@logit(level=INFO2)
def SL(timer: Timer):
    restart(timer)
    GoMainPage(timer)
    timer.set_page('main_page')

@logit(level=INFO3)
def map_fight(timer: Timer, decision_maker: DecisionBlock = None, type='normal', end_page='map_page', *args, **kwargs):
    """处理地图战斗开始出征后(进入战斗地图后)的所有情况

    Args:
        timer (Timer): _description_
        type (str, optional): 战斗类型. Defaults to 'normal'.
        end_page (str, optional): 战斗结束后的位置. Defaults to 'map_page'.
        kwargs: 一些其它参数
    Returns:
        'SL':进行了 SL 操作
    """
    print("map fight start")
    if decision_maker is None:
        decision_maker = timer.defaul_decision_maker

    while(True):
        res = fight(timer, 'map_fight', decision_maker, end_page=end_page, *args, **kwargs)
        if(res == 'map_end'):
            print("map fight end:", timer.chapter, timer.node)
            break
        if(res == 'SL'):
            return 'SL'

        decision = 'proceed'
        value = decision_maker.make_decision(timer, decision, *args, **kwargs)
        choose_decision(timer, decision, value)
        if(value == 0):
            end_page = 'map_page'   # TODO：暂时解决了bug，需要修改
            break

    timer.set_page(end_page)

@logit(level=INFO3)
def fight(timer: Timer, type='map_fight', decision_maker: DecisionBlock = None, *args, **kwargs):
    """处理一个阶段的单点战斗
    包括从上一次出征或继续前进开始,进行的战况选择,索敌,决策是否战斗,战斗,结算获取舰船到选择是否回港的全部过程

    Args:
        timer (Timer): _description_
        type (str, optional): 描述战斗类型. Defaults to 'map_fight'.

    Returns:
        str: 'detour_sucess' 该点迂回成功
        str: 'map_end' 地图结束,当且仅当地图战斗时返回.
        str: 'SL' 进行了 SL 操作
    """
    print("fight of type:", type, "start")
    decision = wait_until_decision(timer, type, *args, **kwargs)
    if(decision == 'fight_condition'):
        choose_decision(timer, decision, decision_maker.make_decision(timer, decision, *args, **kwargs))
        return fight(timer, type, decision_maker, *args, **kwargs)

    if(decision == 'fight_start'):
        timer.ammo -= 2
        timer.oil -= 2

    if (decision == 'fight'):
        formation = decision_maker.make_decision(timer, 'formation', *args, **kwargs)
        if (formation == 0):
            choose_decision(timer, decision, 0)
            return 'map_end'
        elif formation == 6:
            timer.oil -= 1
            if choose_decision(timer, decision, 2):
                return 'detour_success'
        else:
            choose_decision(timer, decision, 1)

        decision = wait_until_decision(timer, type='fight', no_get_enemy=True, no_fight=True)
        print("after choose statu:", decision)

    if(decision == 'formation'):
        value = decision_maker.make_decision(timer, decision, *args, **kwargs)
        res = choose_decision(timer, decision, value)
        if(res == 'SL'):
            return res

        timer.ammo -= 2
        timer.oil -= 2

    fight_during(timer, decision_maker, *args, **kwargs)
    return fight_end(timer, type, *args, **kwargs)
