from wsgr import *
import time
show_all_debug_info()
timer = start_script(to_main_page=True) # 启动模拟器和游戏，得到一个游戏控制器

# ============TEST EVENT=============
"""event_plan = EventFightPlan20220928(timer, r'plans\event\20220929\E10A.yaml')
event_plan.run(same_work=False)
for i in range(100):
    event_plan.run(same_work=True)"""
event_plan2 = EventFightPlan20220928_2(timer, r'plans\event\20220929\E10BB.yaml')
event_plan2.run(same_work=False)
for i in range(100):
    event_plan2.run(same_work=False)




quit()

# ============END=============


# ============TEST BATTLE=============

battleship_battle_plan = BattlePlan(timer, 'plans\\battle\\hard_Battleship.yaml', 'plans\\default.yaml') # 指定 plan 参数和 default 参数
for _ in range(8):
    pass
    battleship_battle_plan.run() # Plan 模块的运行需要调用成员函数 run
                                 # 超出每日战役次数上限后运行会失败，但不会抛出异常
                            
# ===========END=============


# ===========TEST EXERCISE============

exercise_plan = NormalExercisePlan(timer, 'plans\\exercise\\plan_1.yaml', 'plans\\default.yaml')
exercise_plan.run()

# ===========END============


# ===========TEST NORMALFIGHT============

fight_plan_85 = NormalFightPlan(timer, 'plans\\normal_fight\\8-5AI-only1DD.yaml', 'plans\\default.yaml')
for _ in range(10):
    fight_plan_85.run()
    for result in fight_plan_85.fight_recorder.fight_results:
        print(result)
    print(fight_plan_85.fight_recorder)
    
"""NormalFightPlan 模块中的 fight_recorder 成员记录了所有战斗过程
    可以通过该成员查看战斗状态以便进行下一步操作"""

# ===========END============


# ===========TEST EXPEDITION============

"""expedition_recorder = Expedition(timer) # 远征记录模块
for t in range(3600):
    time.sleep(1)
    if(t % 900 == 0): # 900s 检查一次远征
        expedition_recorder.run(force=True) # 进行远征检查并收获
"""
# ===========END============