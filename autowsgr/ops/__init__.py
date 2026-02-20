"""游戏操作层 (GameOps) — 跨页面组合操作。

本模块提供高级游戏操作函数，每个函数封装了涉及多个页面切换的完整业务流程。

与 UI 层的区别:

- **UI 层** (:mod:`autowsgr.ui`): 单页面内的原子操作（识别、点击、状态查询）
- **GameOps 层** (:mod:`autowsgr.ops`): 跨页面导航 + 多个 UI 操作的组合

设计原则:

- **无状态**: 所有函数都是纯函数式的，不维护全局 ``now_page``
- **可组合**: 函数之间通过 ``ctrl`` 串联
- **可测试**: mock ``AndroidController`` 即可单元测试

Usage::

    from autowsgr.ops import goto_page, cook, collect_rewards

    # 回到主页面
    goto_page(ctrl, "主页面")

    # 导航到任意页面
    goto_page(ctrl, "建造页面")

    # 做菜
    cook(ctrl, position=1)

    # 收取任务奖励
    collect_rewards(ctrl)

模块结构::

    ops/
    ├── __init__.py      ← 本文件 (统一导出)
    ├── navigate.py      ← 跨页面导航
    ├── sortie.py        ← 出征准备 (换船、修理策略)
    ├── decisive.py      ← 决战过程控制器
    ├── reward.py        ← 任务奖励
    ├── cook.py          ← 食堂做菜
    ├── destroy.py       ← 解装舰船
    ├── expedition.py    ← 远征收取
    ├── build.py         ← 建造/收取
    ├── repair.py        ← 浴室修理
    └── image_resources.py ← 图像模板资源注册中心
"""

# ── 导航 ──
from autowsgr.ops.navigate import goto_page, identify_current_page

# ── 出征准备 ──
from autowsgr.ops.sortie import RepairStrategy, apply_repair

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

# ── 图像模板资源 ──
from autowsgr.ops.image_resources import Templates

__all__ = [
    # 导航
    # "go_main_page",  # deprecated — use goto_page(ctrl, "主页面") instead
    "goto_page",
    "identify_current_page",
    # 出征准备
    "RepairStrategy",
    "apply_repair",
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
    # 图像模板资源
    "Templates",
]
