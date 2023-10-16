from autowsgr.fight import DecisiveBattle
from autowsgr.scripts.main import start_script

timer = start_script()
decisive_battle = DecisiveBattle(
    timer,
    6,
    1,
    "A",
    level1=["肥鱼", "U-1206", "U-47", "射水鱼", "U-96", "U-1405"],
    level2=["U-81", "大青花鱼"],
    flagship_priority=["U-1405", "U-47"],
)
decisive_battle.start_fight()
