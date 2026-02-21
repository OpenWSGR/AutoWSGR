"""游戏操作层 (GameOps) — 跨页面组合操作。

本模块提供高级游戏操作函数，每个函数封装了涉及多个页面切换的完整业务流程。

与 UI 层的区别:

- **UI 层** (:mod:`autowsgr.ui`): 单页面内的原子操作（识别、点击、状态查询）
- **GameOps 层** (:mod:`autowsgr.ops`): 跨页面导航 + 委托 UI 执行

设计原则:

- **无状态**: 所有函数都是纯函数式的，不维护全局 ``now_page``
- **薄包装**: ops 只负责导航，实际操作全部委托 UI 层
- **可组合**: 函数之间通过 ``ctrl`` 串联
- **可测试**: mock ``AndroidController`` 即可单元测试

模块结构::

    ops/
    ├── __init__.py        ← 本文件 (统一导出)
    ├── navigate.py        ← 跨页面导航
    ├── decisive/          ← 决战过程控制器
    ├── exercise.py        ← 演习战斗
    ├── normal_fight.py    ← 常规战斗 (多节点地图)
    ├── campaign.py        ← 战役战斗 (单点)
    ├── fight.py           ← 简易战斗接口 (ctrl + engine + plan)
    ├── reward.py          ← 任务奖励
    ├── cook.py            ← 食堂做菜
    ├── destroy.py         ← 解装舰船
    ├── expedition.py      ← 远征收取
    ├── build.py           ← 建造/收取
    ├── repair.py          ← 浴室修理
    ├── startup.py         ← 游戏启动与导航到主页面
    └── image_resources.py ← 图像模板资源注册中心
"""

# ── 启动 ──
from autowsgr.ops.startup import (
    ensure_game_ready,
    go_main_page,
    is_game_running,
    is_on_main_page,
    restart_game,
    start_game,
)

# ── 导航 ──
from autowsgr.ops.navigate import goto_page, identify_current_page

# ── 任务奖励 ──
from autowsgr.ops.reward import collect_rewards

# ── 食堂 ──
from autowsgr.ops.cook import cook

# ── 解装 ──
from autowsgr.ops.destroy import destroy_ships

# ── 远征 ──
from autowsgr.ops.expedition import collect_expedition

# ── 建造 ──
from autowsgr.ops.build import BuildRecipe, build_ship, collect_built_ships

# ── 浴室修理 ──
from autowsgr.ops.repair import repair_in_bath

# ── 决战 ──
from autowsgr.ops.decisive import DecisiveConfig, DecisiveController, DecisiveResult

# ── 演习 ──
from autowsgr.ops.exercise import ExerciseRunner, run_exercise
from autowsgr.infra import ExerciseConfig

# ── 常规战斗 ──
from autowsgr.ops.normal_fight import (
    NormalFightRunner,
    run_normal_fight,
    run_normal_fight_from_yaml,
)

# ── 战役 ──
from autowsgr.ops.campaign import CampaignRunner

# ── 简易战斗接口 ──
from autowsgr.ops.fight import run_fight, run_fight_n

# ── 图像模板资源 ──
from autowsgr.ops.image_resources import Templates

__all__ = [
    # 启动
    "ensure_game_ready",
    "go_main_page",
    "is_game_running",
    "is_on_main_page",
    "restart_game",
    "start_game",
    # 导航
    "goto_page",
    "identify_current_page",
    # 任务奖励
    "collect_rewards",
    # 食堂
    "cook",
    # 解装
    "destroy_ships",
    # 远征
    "collect_expedition",
    # 建造
    "BuildRecipe",
    "build_ship",
    "collect_built_ships",
    # 浴室修理
    "repair_in_bath",
    # 决战
    "DecisiveConfig",
    "DecisiveController",
    "DecisiveResult",
    # 演习
    "ExerciseConfig",
    "ExerciseRunner",
    "run_exercise",
    # 常规战斗
    "NormalFightRunner",
    "run_normal_fight",
    "run_normal_fight_from_yaml",
    # 战役
    "CampaignRunner",
    # 简易战斗接口
    "run_fight",
    "run_fight_n",
    # 图像模板资源
    "Templates",
]
