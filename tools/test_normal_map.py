from autowsgr.scripts.main import start_script
from autowsgr.fight import NormalFightPlan
from autowsgr.constants.other_constants import CHAPTER_NODE_COUNT

timer = start_script()
plan = NormalFightPlan(timer, "normal_fight/7-46SS-all.yaml")
for i, nodes  in enumerate(CHAPTER_NODE_COUNT):
    if i <= 0:
        continue
    for j in range(1, nodes + 1):
        plan._change_fight_map(i, j)
print("测试成功!")