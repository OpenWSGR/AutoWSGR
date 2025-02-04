import copy
import datetime
import os
import warnings
from dataclasses import KW_ONLY, asdict, dataclass, field, fields
from typing import Any, Literal, TextIO
from typing_extensions import Self

import rich

from autowsgr.constants.data_roots import DATA_ROOT, OCR_ROOT
from autowsgr.types import (
    DestroyShipWorkMode,
    EmulatorType,
    FightCondition,
    Formation,
    GameAPP,
    OcrBackend,
    OSType,
    RepairMode,
    ShipType,
)


@dataclass(frozen=True)
class BaseConfig:
    _: KW_ONLY

    @classmethod
    def from_dict(cls, data: dict[str, Any], /, **kwargs: Any) -> Self:
        """Create a new instance from a dictionary."""
        data, kwargs = {**data, **kwargs}, {}
        for f in fields(cls):
            if f.name in data and f.init:
                if f.name in ATTRIBUTE_RECURSIVE:
                    if f.type is list:
                        kwargs[f.name] = [
                            ATTRIBUTE_RECURSIVE[f.name].from_dict(d) for d in data.pop(f.name)
                        ]
                    else:
                        kwargs[f.name] = ATTRIBUTE_RECURSIVE[f.name].from_dict(data.pop(f.name))
                else:
                    kwargs[f.name] = data.pop(f.name)

        self = cls(**kwargs)
        sentinel = object()
        for key, value in data.items():
            if key in ATTRIBUTE_IGNORE:
                continue
            self_value = getattr(self, key, sentinel)
            if self_value is sentinel:
                warnings.warn(f'Unexpected key: {key!r}', stacklevel=2)
                object.__setattr__(self, key, value)
            elif self_value != value:
                raise ValueError(
                    f'Conflicting values for key: {key!r}, got {value!r} and already had {self_value!r}.',
                )

        return self

    def asdict(self) -> dict[str, Any]:
        """Convert the instance to a dictionary."""
        return asdict(self)

    def __replace__(self, **kwargs: Any) -> Self:
        """Replace the attributes with the given values."""
        replaced = copy.copy(self)
        for key, value in kwargs.items():
            object.__setattr__(replaced, key, value)
        return replaced

    def pprint(self, file: TextIO | None = None) -> None:
        """Pretty print the instance."""
        rich.print(self, file=file)


@dataclass(frozen=True)
class DailyAutomationConfig(BaseConfig):
    # Routine
    auto_expedition: bool = True
    """自动重复远征"""
    auto_gain_bonus: bool = True
    """当有任务完成时自动点击"""
    auto_bath_repair: bool = True
    """空闲时自动澡堂修理"""
    auto_set_support: bool = False
    """自动开启战役支援"""
    auto_battle: bool = True
    """自动打完每日战役次数"""
    battle_type: Literal[
        '简单航母',
        '简单潜艇',
        '简单驱逐',
        '简单巡洋',
        '简单战列',
        '困难航母',
        '困难潜艇',
        '困难驱逐',
        '困难巡洋',
        '困难战列',
    ] = '困难潜艇'
    """打哪个战役"""
    auto_exercise: bool = True
    """自动打完每日的三次演习"""
    exercise_fleet_id: int | None = None
    """演习出征舰队"""

    # 常规战
    auto_normal_fight: bool = True
    """按自定义任务进行常规战"""
    normal_fight_tasks: list[str] = field(default_factory=list)
    """常规战任务列表"""
    quick_repair_limit: int | None = None
    """快修消耗上限，达到时终止常规战出征。不填则无上限"""
    stop_max_ship: bool = False
    """是否获取完当天上限500船后终止常规战出征"""
    stop_max_loot: bool = False
    """是否获取完当天上限50胖次后终止常规战出征"""


@dataclass(frozen=True)
class DecisiveBattleConfig(BaseConfig):
    chapter: int = 6
    """决战章节,请保证为 [1, 6] 中的整数. Defaults to 6."""
    level1: list[str] | None = None
    """一级舰队"""
    level2: list[str] | None = None
    """二级舰队"""
    flagship_priority: list[str] | None = None
    """旗舰优先级队列"""
    repair_level: int = 1
    """维修策略, 1 为中破修, 2 为大破修"""
    full_destroy: bool = False
    """是否船舱满了解装舰船（仅限决战）"""

    def __post_init__(self) -> None:
        assert 1 <= self.chapter <= 6, '决战章节必须为 [1, 6] 中的整数'
        if self.level1 is None:
            object.__setattr__(
                self,
                'level1',
                ['鲃鱼', 'U-1206', 'U-47', '射水鱼', 'U-96', 'U-1405'],
            )
        if self.level2 is None:
            object.__setattr__(self, 'level2', ['U-81', '大青花鱼'])
        if self.flagship_priority is None:
            object.__setattr__(self, 'flagship_priority', ['U-1405', 'U-47', 'U-96', 'U-1206'])


@dataclass(frozen=True)
class UserConfig(BaseConfig):
    # 系统
    os_type: OSType = field(init=False)
    """操作系统类型。自动设置"""

    # 模拟器
    emulator_type: EmulatorType = EmulatorType.leidian
    """模拟器类型。mumu模拟器现在截图效率较低，后续会进行优化"""
    emulator_name: str | None = None
    """模拟器链接地址。不填则自动设置"""
    emulator_start_cmd: str | None = None
    """模拟器exe地址。如果留空则自动从注册表中查询。示例: C:/leidian/LDPlayer9/dnplayer.exe"""
    emulator_process_name: str | None = None
    """模拟器进程名。不填则自动设置"""

    # 游戏
    game_app: GameAPP = GameAPP.official
    """游戏版本。"""
    app_name: str = field(init=False)
    """游戏应用名。自动设置"""
    account: str | None = None
    """游戏账号"""
    password: str | None = None
    """游戏密码"""

    # 脚本行为
    ocr_backend: OcrBackend = OcrBackend.easyocr
    """文字识别后端。TODO: 暂时仅easyocr没问题"""
    delay: float = 1.5
    """延迟时间基本单位，单位为秒。如果模拟器卡顿可调高"""
    check_update: bool = True
    """脚本自动检查更新"""
    check_page: bool = True
    """是否在启动时检查游戏页面"""
    dock_full_destroy: bool = True
    """船坞已满时自动清空, 若设置为false则船坞已满后终止所有常规出征任务"""
    bathroom_feature_count: int = 1
    """浴室数(购买的浴室装饰数, 最大为 3) TODO: 可自动获取"""
    bathroom_count: int = 2
    """修理位置总数(最大为 12) TODO: 可自动获取"""
    default_plan_root: str = field(init=False)
    """默认计划文件根目录。"""
    plan_root: str | None = None
    """计划文件根目录。可部分覆盖default_plan_root中的文件"""
    default_ship_name_file: str = field(init=False)
    """默认舰船名文件。"""
    ship_name_file: str | None = None
    """舰船名文件。不填写则使用default_ship_name_file"""
    destroy_ship_work_mode: DestroyShipWorkMode = DestroyShipWorkMode.disable
    """解装舰船的工作模式. disable 是不启用舰种分类, include 为只解装指定舰种, exclude 为解装除指定舰种外的所有舰种"""
    destroy_ship_types: list[ShipType] = field(default_factory=list)
    """指定舰种, 参照 autowsgr/types.py 中 #191 行的 ShipType, 使用中文"""

    # Log
    log_root: str = 'log'
    """日志保存根目录"""
    log_dir: str = field(init=False)
    """日志保存路径。自动创建日期文件夹。"""
    debug: bool = True
    """是否开启调试模式，如果为 True, 则会输出更多的调试信息。"""
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'DEBUG'
    """调试模式log_level应该设置为DEBUG"""
    show_map_node: bool = False
    """是否显示地图节点信息。"""
    show_android_input: bool = True
    """是否显示 Android 输入的信息。"""
    show_enemy_rules: bool = True
    """是否显示敌人规则。"""
    show_fight_stage: bool = True
    """是否显示战斗阶段。"""
    show_chapter_info: bool = True
    """是否显示章节信息。"""
    show_match_fight_stage: bool = True
    """是否显示匹配战斗阶段。"""
    show_decisive_battle_info: bool = True
    """是否显示决战信息。"""
    show_ocr_info: bool = True
    """是否显示OCR信息。"""

    # 嵌套的下层配置
    daily_automation: DailyAutomationConfig | None = None
    """日常自动化配置"""
    decisive_battle: DecisiveBattleConfig | None = None
    """决战自动化配置"""

    def __post_init__(self) -> None:
        # 确保类型正确
        object.__setattr__(self, 'emulator_type', EmulatorType(self.emulator_type))
        object.__setattr__(self, 'game_app', GameAPP(self.game_app))
        object.__setattr__(self, 'ocr_backend', OcrBackend(self.ocr_backend))
        object.__setattr__(
            self,
            'destroy_ship_work_mode',
            DestroyShipWorkMode(self.destroy_ship_work_mode),
        )
        if self.destroy_ship_types is None:
            object.__setattr__(self, 'destroy_ship_types', [])
        else:
            object.__setattr__(
                self,
                'destroy_ship_types',
                [ShipType(t) for t in self.destroy_ship_types],
            )

        # 系统
        object.__setattr__(self, 'os_type', OSType.auto())

        # 模拟器
        if self.emulator_name is None:
            object.__setattr__(
                self,
                'emulator_name',
                self.emulator_type.default_emulator_name(self.os_type),
            )
        if self.emulator_start_cmd is None:
            object.__setattr__(
                self,
                'emulator_start_cmd',
                self.emulator_type.auto_emulator_path(self.os_type),
            )
        if self.emulator_process_name is None:
            object.__setattr__(
                self,
                'emulator_process_name',
                os.path.basename(self.emulator_start_cmd),
            )

        # 游戏
        object.__setattr__(self, 'app_name', self.game_app.app_name)

        # 设置plan_root
        object.__setattr__(self, 'default_plan_root', os.path.join(DATA_ROOT, 'plans'))
        if self.plan_root is None:
            local_plan_root = os.path.join(os.getcwd(), 'plans')
            if os.path.exists(local_plan_root):
                object.__setattr__(self, 'plan_root', local_plan_root)
                print(f'使用脚本运行目录的plans: {local_plan_root}')
            else:
                object.__setattr__(self, 'plan_root', self.default_plan_root)
                print(f'使用默认plans: {self.default_plan_root}')

        # 加载舰船名文件
        object.__setattr__(self, 'default_ship_name_file', os.path.join(OCR_ROOT, 'ship_name.yaml'))
        if self.ship_name_file is None:
            local_ship_name_file = os.path.join(os.getcwd(), 'ship_name.yaml')
            if os.path.exists(local_ship_name_file):
                object.__setattr__(self, 'ship_name_file', local_ship_name_file)
                print(f'使用本地ship_name: {local_ship_name_file}')
            else:
                object.__setattr__(self, 'ship_name_file', self.default_ship_name_file)
                print(f'使用默认ship_name: {self.default_ship_name_file}')

        # 日志
        object.__setattr__(
            self,
            'log_dir',
            os.path.join(self.log_root, datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')),
        )


@dataclass(frozen=True)
class FightConfig(BaseConfig):
    chapter: int | str = 1
    """章节号"""
    map: int | str = 1
    """地图号"""
    fleet_id: int = 1
    """舰队号"""
    fleet: list[str] | None = None
    """舰队成员 (按名字区分), 为 None 则不变
        fleet: ["", "吹雪", "明斯克", "胡德", "赤诚", "",]
        填 "" 或者不填则代表该位置无舰船 0 号位(第一个)填 "" 占位
        上例的舰队最终为: 吹雪 明斯克 胡德 赤诚 5号位无舰船 6号位无舰船
        现有策略填写时用的作者的船舱名, 记得修改
    """
    repair_mode: RepairMode | list[RepairMode] = RepairMode.severe_damage
    """修理方案。1:中破就修 2:只修大破；也可以用列表指定6个位置不同修理方案"""
    selected_nodes: list[str] = field(default_factory=list)
    """选择要打的节点，白名单模式，一旦到达不要的节点就SL"""
    fight_condition: FightCondition = FightCondition.aim
    """战况选择。1.稳步前进 2.火力万岁 3.小心翼翼 4.瞄准 5.搜索阵型"""

    # 活动专属
    from_alpha: bool = True
    """入口选择。True 为从 alpha 入口进入, False 为从 beta 入口进入"""

    def __post_init__(self) -> None:
        if isinstance(self.repair_mode, list):
            object.__setattr__(self, 'repair_mode', [RepairMode(r) for r in self.repair_mode])
        else:
            object.__setattr__(
                self,
                'repair_mode',
                [RepairMode(self.repair_mode) for _ in range(6)],
            )

        object.__setattr__(self, 'fight_condition', FightCondition(self.fight_condition))


@dataclass(frozen=True)
class BattleConfig(FightConfig):
    repair_mode: RepairMode | list[RepairMode] = RepairMode.moderate_damage
    """修理方案。1:中破就修 2:只修大破；也可以用列表指定6个位置不同修理方案"""


@dataclass(frozen=True)
class ExerciseConfig(FightConfig):
    selected_nodes: list[str] = field(default_factory=lambda: ['player', 'robot'])
    """仅使用默认值"""
    discard: bool = False
    """TODO: 检查逻辑"""
    exercise_times: int = 4
    """最大玩家演习次数"""
    robot: bool = True
    """是否打机器人"""
    max_refresh_times: int = 2
    """最大刷新次数"""


# @dataclass(frozen=True)
# class EnemyRule(BaseConfig):
#     condition: str
#     """触发条件"""
#     action: SearchEnemyAction | Formation
#     """进行动作，或者选择阵型"""

#     def __post_init__(self) -> None:
#         if isinstance(self.action, int):
#             object.__setattr__(self, 'action', Formation(self.action))
#         else:
#             object.__setattr__(self, 'action', SearchEnemyAction(self.action))


@dataclass(frozen=True)
class NodeConfig(BaseConfig):
    # 索敌阶段
    long_missile_support: bool = False
    """（当存在时）是否开启导巡的远程导弹支援"""
    detour: bool = False
    """（当存在时）是否进行迂回"""
    enemy_rules: list[str] = field(default_factory=list)
    """每条按照 ["(类型 符号 数量) and/or ()", "操作"] 的字符串形式给出，从上到下执行第一条符合的命令。
    类型：舰船类型；符号：[>=、<=、>、<、==、!=]；数量：数字；
    操作：[retreat、detour、阵型数字(1-5)]
    如果在这里做了阵型选择决定，则优先级将高过下面的阵型选择。例子：["(SS >= 2)", 5]
    and 的优先级高于 or"""

    # 阵型选择阶段
    SL_when_spot_enemy_fails: bool = False
    """索敌失败时是否SL"""
    SL_when_detour_fails: bool = True
    """迂回失败是否退出"""
    SL_when_enter_fight: bool = False
    """进入战斗是否退出"""
    formation: Formation = Formation.double_column
    """阵型选择"""
    formation_when_spot_enemy_fails: Formation | None = None
    """索敌失败时阵型选择"""

    # 夜战, 前进阶段
    night: bool = False
    """是否夜战"""
    proceed: bool = True
    """是否前进"""
    proceed_stop: RepairMode | list[RepairMode] = RepairMode.severe_damage
    """达到指定破损状态时结束。1:中破 2:大破；也可以用列表指定6个位置不同"""

    def __post_init__(self) -> None:
        object.__setattr__(self, 'formation', Formation(self.formation))
        if self.formation_when_spot_enemy_fails is not None:
            object.__setattr__(
                self,
                'formation_when_spot_enemy_fails',
                Formation(self.formation_when_spot_enemy_fails),
            )
        if isinstance(self.proceed_stop, list):
            object.__setattr__(self, 'proceed_stop', [RepairMode[r] for r in self.proceed_stop])
        else:
            object.__setattr__(
                self,
                'proceed_stop',
                [RepairMode(self.proceed_stop) for _ in range(6)],
            )


ATTRIBUTE_RECURSIVE = {
    'daily_automation': DailyAutomationConfig,
    'decisive_battle': DecisiveBattleConfig,
    # {'enemy_rules': EnemyRule},
}
ATTRIBUTE_IGNORE = {
    'node_defaults',
    'node_args',
}
