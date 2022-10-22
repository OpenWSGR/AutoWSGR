import time

from AutoWSGR.constants.settings import S
from AutoWSGR.fight.battle import BattlePlan
from AutoWSGR.fight.normal_fight import NormalFightPlan
from AutoWSGR.game.game_operation import Expedition, GainBounds, RepairByBath
from AutoWSGR.main import start_script


class DailyOperation:
    def __init__(self, setting_path) -> None:
        self.timer = start_script(setting_path)
        S.DEBUG = False

        if S.Auto_Expedition:
            self.expedition_plan = Expedition(self.timer)

        if S.Auto_Battle:
            self.battle_plan = BattlePlan(self.timer, plan_path=f'battle/{S.Battle_Name}.yaml')

        if type(S.Auto_NormalFight) == list and S.Auto_NormalFight:
            self.fight_plans = []
            self.fight_complete_times = []
            for plan in S.Auto_NormalFight:
                self.fight_plans.append(NormalFightPlan(self.timer, plan_path=f"normal_fight/{plan[0]}.yaml", fleet_id=plan[1]))
                self.fight_complete_times.append([0, plan[2]])  # 二元组， [已完成次数, 目标次数]

        self.start_time = self.last_time = time.time()

    def _has_unfinished(self):
        return any(times[0] < times[1] for times in self.fight_complete_times)

    def _get_unfinished(self):
        for i, times in enumerate(self.fight_complete_times):
            if times[0] < times[1]:
                return i

    def _normal_fight_once(self, task_id):
        plan = self.fight_plans[task_id]
        ret = plan.run()
        if ret == "success":
            self.fight_complete_times[task_id][0] += 1

    def run(self):
        # 自动战役，直到超过次数
        if S.Auto_Battle:
            ret = "success"
            while ret == "success":
                ret = self.battle_plan.run()

        # 自动出征
        if type(S.Auto_NormalFight) == list and S.Auto_NormalFight:
            while self._has_unfinished():
                task_id = self._get_unfinished()
                self._normal_fight_once(task_id)

                if time.time() - self.last_time >= 5*60:
                    self._expedition()
                    self._gain_bonus()
                    self.last_time = time.time()

        # 自动远征
        while True:
            self._bath_repair()
            self._expedition()
            self._gain_bonus()
            time.sleep(360)

    def _expedition(self):
        if S.Auto_Expedition:
            self.expedition_plan.run(True)

    def _gain_bonus(self):
        if S.Auto_Gain_Bonous:
            GainBounds(self.timer)

    def _bath_repair(self):
        if S.Auto_Bath_Repair:
            RepairByBath(self.timer)
