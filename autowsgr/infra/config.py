"""配置管理 — 基于 Pydantic v2。

配置从 YAML 文件加载，经过 Pydantic 校验后生成不可变的配置对象。
"""

from __future__ import annotations

import datetime
import os
import random
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from autowsgr.infra.logger import get_logger
from autowsgr.types import (
    DestroyShipWorkMode,
    EmulatorType,
    GameAPP,
    OcrMirror,
    OSType,
    RepairMode,
    ShipType,
)

from .file_utils import load_yaml


_log = get_logger('infra')

# ── 全局操作延迟 ──
# 这里引入了两个变量会自动判断谁大谁小，意思呢就是说可以通过这个来控制UI操作之后的延迟时间，默认不开启这个延迟如果有需要可以自己调
# 影响 scrcpy 设备交互操作（click/swipe/key_event/text/start_app/stop_app）
OPERATION_DELAY_MIN: float = 0.0
OPERATION_DELAY_MAX: float = 0.0


def operation_delay() -> float:
    """本次 UI 操作后的随机延迟秒数。

    受 :data:`OPERATION_DELAY_MIN` / :data:`OPERATION_DELAY_MAX` 控制。
    兼容层把 classic 的 ``delay`` 单值映射为 ``MIN = MAX = delay``;
    本函数读取模块全局, 故运行期修改 :data:`OPERATION_DELAY_MIN/MAX` 即时生效
    (``scrcpy.py`` 通过调用本函数而非 ``from import`` 绑定值)。
    """
    return random.uniform(
        min(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
        max(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
    )


# ── 基础运行配置 ──


class EmulatorConfig(BaseModel):
    """模拟器配置。"""

    model_config = {'frozen': True}

    type: EmulatorType = EmulatorType.leidian
    """模拟器类型"""
    path: str | None = None
    """模拟器可执行文件路径。None = 自动检测"""
    serial: str | None = None
    """ADB serial 地址。None = 自动检测"""
    process_name: str | None = None
    """模拟器进程名。None = 自动推断"""


class AccountConfig(BaseModel):
    """游戏账号配置。"""

    model_config = {'frozen': True}

    game_app: GameAPP = GameAPP.official
    """游戏渠道(决定 Android 包名)"""

    @property
    def package_name(self) -> str:
        """Android 包名。"""
        return self.game_app.package_name


class OCRConfig(BaseModel):
    """OCR 引擎配置。"""

    model_config = {'frozen': True}

    gpu: bool = False
    """是否使用 GPU 加速"""
    mirror: OcrMirror = OcrMirror.modelscope
    """EasyOCR 模型下载镜像源"""
    enhanced_ship_ocr: bool = False
    """是否启用增强船只识别 OCR (FastOCR + PP-OCRv6-small)。默认关闭；
    开启后船只名称、等级和舰种识别节点优先使用内置 FastOCR 模型。"""

    # 舰名匹配
    ship_name_match_confidence: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )
    """舰名匹配置信度：0 为关闭，0.65 为默认，1 为完全匹配；越大越严格，建议勿改。"""
    ship_name_corrections: dict[str, str] = Field(default_factory=dict)
    """用户舰名 OCR 修正规则，格式为 ``OCR 原文: SHIPNAMES 标准舰名``。"""
    ship_name_aliases: dict[str, str] = Field(default_factory=dict)
    """用户舰名别名，格式为 ``用户自定义名: SHIPNAMES 标准舰名``。"""

    @field_validator('ship_name_corrections', 'ship_name_aliases', mode='before')
    @classmethod
    def _normalize_ship_name_corrections(cls, value: object) -> dict[str, str]:
        """逐条清理用户舰名配置；格式错误的条目直接跳过。"""
        if value is None:
            return {}
        if not isinstance(value, dict):
            _log.warning('OCR 用户舰名配置必须是映射，已跳过全部配置')
            return {}

        corrections: dict[str, str] = {}
        for raw_text, ship_name in value.items():
            if not isinstance(raw_text, str) or not isinstance(ship_name, str):
                _log.warning('跳过格式错误的 OCR 用户舰名配置: {} -> {}', raw_text, ship_name)
                continue
            source = raw_text.strip()
            target = ship_name.strip()
            if not source or not target:
                _log.warning('跳过内容为空的 OCR 用户舰名配置')
                continue
            corrections[source] = target
        return corrections


class LogConfig(BaseModel):
    """日志配置。"""

    model_config = {'frozen': True}

    level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'DEBUG'
    """日志级别"""
    root: Path = Path('logs')
    """日志保存根目录"""
    dir: Path | None = None
    """日志保存路径。自动按日期生成"""

    # 细粒度显示开关 (仅保留有效开关; classic 遗留的 show_map_node /
    # show_android_input / show_enemy_rules / show_fight_stage /
    # show_chapter_info / show_match_fight_stage / show_ocr_info 已移除)
    show_decisive_battle_info: bool = True
    show_emulator_debug: bool = True
    """是否输出 emulator 通道的 DEBUG 日志（click/swipe 等操作）。"""
    show_ui_debug: bool = True
    """是否输出 ui 通道的 DEBUG 日志（页面识别/等待轮询）。"""
    show_vision_debug: bool = True
    """是否输出 vision 通道的 DEBUG 日志（模板匹配规则结果）。"""
    show_ops_debug: bool = True
    """是否输出 ops 通道的 DEBUG 日志（页面导航/操作重试）。"""
    show_combat_state_debug: bool = True
    """是否输出战斗状态机转移 DEBUG 日志（当前状态→候选列表）。对应通道 combat.engine。"""
    show_combat_recognition_debug: bool = True
    """是否输出战斗识别 DEBUG 日志（匹配到状态、DLL 返回、敌方编成）。对应通道 combat.recognition。"""
    channels: dict[str, str] = {}
    """通道级别覆盖。键为通道名（支持前缀匹配），值为级别字符串，如
    ``{"vision.pixel": "TRACE", "emulator": "INFO"}``。
    详见 :func:`~autowsgr.infra.logger.setup_logger`。
    此处的显式配置优先级高于上方所有 show_*_debug 布尔开关。"""

    @model_validator(mode='after')
    def _set_log_dir(self) -> LogConfig:
        if self.dir is None:
            ts = datetime.datetime.now(tz=datetime.UTC).strftime('%Y-%m-%d_%H-%M-%S')
            object.__setattr__(self, 'dir', self.root / ts)
        return self

    @property
    def effective_channels(self) -> dict[str, str]:
        """合并布尔开关与显式 channels 配置，生成最终通道级别字典。

        布尔开关优先级低于 ``channels`` 中的显式覆盖：若用户在
        ``channels`` 里单独设置了 ``"emulator": "DEBUG"``，即使
        ``show_emulator_debug=False`` 也仍生效。
        """
        merged: dict[str, str] = {}
        if not self.show_emulator_debug:
            merged['emulator'] = 'INFO'
        if not self.show_ui_debug:
            merged['ui'] = 'INFO'
        if not self.show_vision_debug:
            merged['vision'] = 'INFO'
        if not self.show_ops_debug:
            merged['ops'] = 'INFO'
        if not self.show_combat_state_debug:
            merged['combat.engine'] = 'INFO'
        if not self.show_combat_recognition_debug:
            merged['combat.recognition'] = 'INFO'

        # 决战调试：show_decisive_battle_info 为 True 时，即使父通道
        # (ui / ops) 被设为 INFO，也要让决战子通道输出 DEBUG 日志。
        if self.show_decisive_battle_info:
            merged['decisive'] = 'DEBUG'
            merged['ops.decisive'] = 'DEBUG'
            merged['ui.decisive'] = 'DEBUG'

        # 显式 channels 配置覆盖布尔开关
        merged.update(self.channels)
        return merged


# ── 自动化任务配置 ──
class NormalFightTaskConfig(BaseModel):
    """单个常规战任务配置。

    兼容 classic 的 ``[plan_name, fleet_id, target_times]`` 列表写法
    (经 :func:`_parse_normal_fight_tasks` 解析), 也支持纯字符串 (仅 plan 名)
    或完整字典。
    """

    model_config = {'frozen': True}

    name: str
    """常规战计划名 (如 ``8-5AI-only1DD``), 解析为 ``autowsgr/data/plan/normal_fight/`` 下的文件。"""
    fleet_id: int | None = None
    """出征舰队编号; 留空则用 plan 内配置。"""
    times: int | None = None
    """目标出击次数; ``None`` 表示无限 (空闲填充, 仅受全局上限约束)。

    .. note:: ``times=None`` (无限) 且未开启 ``stop_max_ship`` /
       ``stop_max_loot`` / ``quick_repair_limit`` 任一上限时, 常规战会持续
       产出任务、永远抢占浴室修理 (优先级更低), 致浴室修理永不执行。
    """


class DailyAutomationConfig(BaseModel):
    """日常自动化设置。"""

    model_config = {'frozen': True}

    # 基础日常
    auto_expedition: bool = True
    """自动重复远征"""
    auto_gain_bonus: bool = True
    """任务完成时自动点击"""
    auto_bath_repair: bool = True
    """空闲时自动澡堂修理"""
    auto_set_support: bool = False
    """自动开启战役支援"""
    bath_repair_blacklist: list[str] = Field(default_factory=list)
    """浴室修理黑名单:这些舰船名(中文全名)不会被自动浴室修理。"""

    # 战役
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

    # 演习
    auto_exercise: bool = True
    """自动打完每日三次演习"""
    exercise_fleet_id: int | None = None
    """演习出征舰队"""

    # 常规战
    auto_normal_fight: bool = True
    """按自定义任务进行常规战"""
    normal_fight_tasks: list[NormalFightTaskConfig] = Field(default_factory=list)
    """常规战任务列表; 兼容 classic ``[name, fleet, times]`` 写法 (见下方校验器)。"""
    quick_repair_limit: int | None = None
    """快修消耗上限"""
    stop_max_ship: bool = False
    """获取当天上限 500 船后终止"""
    stop_max_loot: bool = False
    """获取当天上限 50 胖次后终止"""

    @field_validator('normal_fight_tasks', mode='before')
    @classmethod
    def _parse_normal_fight_tasks(cls, v: object) -> list[dict[str, Any]]:
        """把 classic ``[name, fleet, times]`` 列表 / 纯字符串 / dict 统一成 dict。

        classic 的 user_settings.yaml 里写法是::

            normal_fight_tasks:
              - [8-5AI-only1DD, 4, 900]   # [plan, fleet_id, target_times]

        Pydantic 默认无法把嵌套 list 塞进结构化模型, 这里在校验前转换。
        """
        if v is None:
            return []
        if not isinstance(v, list):
            raise TypeError(f'normal_fight_tasks 应为列表, 得到 {type(v).__name__}')
        result: list[dict[str, Any]] = []
        for item in v:
            if isinstance(item, str):
                result.append({'name': item})
            elif isinstance(item, dict):
                result.append(item)
            elif isinstance(item, (list, tuple)):
                # [name, fleet_id, target_times]
                if len(item) < 1:
                    raise ValueError(f'常规战任务条目不能为空: {item!r}')
                entry: dict[str, Any] = {'name': str(item[0])}
                if len(item) >= 2 and item[1] is not None:
                    entry['fleet_id'] = int(item[1])  # type: ignore[arg-type]
                if len(item) >= 3 and item[2] is not None:
                    entry['times'] = int(item[2])  # type: ignore[arg-type]
                result.append(entry)
            else:
                raise TypeError(f'无法识别的常规战任务条目: {item!r}')
        return result


class DecisiveConfig(BaseModel):
    """决战自动化配置。"""

    model_config = {'frozen': True}

    chapter: int = 6
    """决战章节 (1-6)"""
    decisive_rounds: int = 1
    """决战连续执行轮数"""
    use_new_fleet_change_algorithm: bool = False
    """决战是否使用新的换船算法；关闭时继续使用原有流程。"""
    level1: list[str] = Field(
        default_factory=lambda: ['鲃鱼', 'U-1206', 'U-47', '射水鱼', 'U-96', 'U-1405']
    )
    """一级舰队"""
    level2: list[str] = Field(default_factory=lambda: ['U-81', '大青花鱼'])
    """二级舰队"""
    flagship_priority: list[str] = Field(
        default_factory=lambda: ['U-1405', 'U-47', 'U-96', 'U-1206']
    )
    """旗舰优先级队列"""
    repair_level: int = 1
    """维修策略 (1=中破修, 2=大破修)"""
    use_quick_repair: bool = True
    """是否使用快修"""
    full_destroy: bool = False
    """船舱满了是否解装舰船"""
    useful_skill: bool = False
    """充分利用技能, 开启时要求地图1必须为Lv1+Lv2中的船; 其余地图至少一半的船为Lv1中的船"""
    useful_skill_strict: bool = False
    """严格利用技能, 开启时要求地图1技能不能获取+1的船; useful_skill为True时本设置才生效"""

    @field_validator('chapter')
    @classmethod
    def _validate_chapter(cls, v: int) -> int:
        if not 1 <= v <= 6:
            raise ValueError('决战章节必须为 1-6 之间的整数')
        return v


# ── 顶层用户配置 ──


class UserConfig(BaseModel):
    """用户配置（顶层聚合）。"""

    model_config = {'frozen': True}

    # 子配置块
    emulator: EmulatorConfig = Field(default_factory=EmulatorConfig)
    account: AccountConfig = Field(default_factory=AccountConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    log: LogConfig = Field(default_factory=LogConfig)
    daily_automation: DailyAutomationConfig | None = None
    decisive_battle: DecisiveConfig | None = None

    # 系统（自动检测）
    os_type: OSType = Field(default_factory=OSType.auto)
    """操作系统类型，自动检测"""

    # 脚本行为
    # classic 的 delay 已移除: 运行期检测到会崩溃提示迁移 (见 config_compat);
    # 新版用 operation_delay_min/max 字段, 由 _apply_operation_delay 写回模块
    # 全局 OPERATION_DELAY_MIN/MAX (供 operation_delay() 读取)。
    # check_page 功能已由 launcher.ensure_ready 覆盖。
    operation_delay_min: float = 0.0
    """UI 操作后随机延迟下界 (秒)。兼容层把 classic 的 delay 同时迁为本字段与 _max。"""
    operation_delay_max: float = 0.0
    """UI 操作后随机延迟上界 (秒)。"""
    dock_full_destroy: bool = True
    """船坞满时自动清空"""
    repair_manually: bool = False
    """是否手动修理"""
    bathroom_count: int = 2
    """修理位置总数 (≤12)。预留:智能浴场空位调度用。"""

    # 解装设置
    destroy_ship_work_mode: DestroyShipWorkMode = DestroyShipWorkMode.disable
    """解装工作模式"""
    destroy_ship_types: list[ShipType] = Field(default_factory=list)
    """指定舰种列表"""
    remove_equipment_mode: bool = True
    """默认卸下装备"""

    @field_validator('destroy_ship_work_mode', mode='before')
    @classmethod
    def _coerce_destroy_mode(cls, v: object) -> object:
        """允许用中文别名或英文成员名指定解装模式。"""
        _alias: dict[str, int] = {
            '不启用': 0,
            'disable': 0,
            '黑名单': 1,
            'include': 1,
            '白名单': 2,
            'exclude': 2,
        }
        if isinstance(v, str):
            key = v.strip()
            if key in _alias:
                return _alias[key]
            # 纯数字字符串也兼容
            if key.isdigit():
                return int(key)
        return v

    # 数据路径
    plan_root: Path | None = None
    """自定义计划文件目录"""
    # ship_name_file 已移除 (新版无需自定义舰船名文件; 兼容层会提示用户删除)

    @model_validator(mode='after')
    def _resolve_emulator_defaults(self) -> UserConfig:
        """自动填充模拟器 serial、path、process_name。"""
        emu = self.emulator
        os_type = self.os_type

        updates: dict[str, Any] = {}

        if os_type == OSType.linux:
            # WSL 需要用户显式配置
            if emu.serial is None:
                raise ValueError('WSL 需要显式设置 emulator.serial')
            if emu.path is None:
                raise ValueError('WSL 需要显式设置 emulator.path')
            if emu.process_name is None:
                updates['process_name'] = os.path.basename(emu.path)
        else:
            if emu.serial is None:
                updates['serial'] = emu.type.default_emulator_name(os_type)
            if emu.path is None:
                try:
                    updates['path'] = emu.type.auto_emulator_path(os_type)
                except (ValueError, FileNotFoundError) as e:
                    _log.warning('自动检测模拟器路径失败: {}', e)
            resolved_path = updates.get('path', emu.path)
            if emu.process_name is None and resolved_path is not None:
                updates['process_name'] = os.path.basename(str(resolved_path))

        if updates:
            new_emu = emu.model_copy(update=updates)
            object.__setattr__(self, 'emulator', new_emu)

        return self

    @model_validator(mode='after')
    def _apply_operation_delay(self) -> UserConfig:
        """把 operation_delay_min/max 写回模块全局, 供 operation_delay() 读取。

        classic 的 ``delay`` 由迁移工具迁为本字段; 这样延迟值随配置持久化,
        不会再因「迁移回写删字段」而丢失。运行期修改这两个全局即时生效
        (``scrcpy.py`` 通过调用 :func:`operation_delay` 而非 ``from import`` 绑定值)。
        """
        global OPERATION_DELAY_MIN, OPERATION_DELAY_MAX  # noqa: PLW0603
        OPERATION_DELAY_MIN = self.operation_delay_min
        OPERATION_DELAY_MAX = self.operation_delay_max
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> UserConfig:
        """从 YAML 文件加载配置。

        raw dict 先经 :func:`detect_legacy_user_config` 检测 classic 老版本字段;
        命中则抛 :class:`LegacyConfigError` 提示用户运行迁移工具
        (``tools/migrate_config.py``), **不再自动迁移 / 回写**。干净则交 Pydantic 校验。
        """
        from autowsgr.infra.config_compat import (
            LegacyConfigError,
            detect_legacy_user_config,
        )

        data = load_yaml(path)
        legacy = detect_legacy_user_config(data)
        if legacy:
            raise LegacyConfigError(
                f'配置文件 {path} 含 classic 老版本字段, 拒绝加载:\n  - '
                + '\n  - '.join(legacy)
                + '\n请先运行迁移工具生成新配置 (原文件不动):\n'
                f'  python tools/migrate_config.py --usersettings "{path}"\n'
                '(可加 --planroot <计划目录> 一起迁移; 默认输出到 migrated_config/)',
            )
        return cls.model_validate(data)


# ── 战斗相关配置 ──
class NodeConfig(BaseModel):
    """单个地图节点的战斗配置。"""

    model_config = {'frozen': True}

    # 索敌阶段
    long_missile_support: bool = False
    """是否开启远程导弹支援"""
    detour: bool = False
    """是否进行迂回"""
    enemy_rules: list[str | list] = Field(default_factory=list)
    """索敌规则列表"""
    enemy_formation_rules: list[str | list] = Field(default_factory=list)
    """阵型规则（优先级高于 enemy_rules）"""

    SL_when_spot_enemy_fails: bool = False
    """索敌失败时是否 SL"""
    SL_when_detour_fails: bool = True
    """迂回失败是否退出"""
    SL_when_enter_fight: bool = False
    """进入战斗是否退出"""

    # 阵型选择
    formation: int = 2
    """阵型 (1-5)"""
    formation_when_spot_enemy_fails: int | None = None
    """索敌失败时的阵型"""

    # 夜战 & 前进
    night: bool = False
    """是否夜战"""
    proceed: bool = True
    """是否前进"""
    proceed_stop: RepairMode | list[RepairMode] = RepairMode.severe_damage
    """达到指定破损状态时停止前进"""
    grade: str = ''
    """本节点要求的最低战果等级 (D/C/B/A/S/SS), 空 = 无要求"""


class FightConfig(BaseModel):
    """出征配置（通用）。"""

    model_config = {'frozen': True}

    chapter: int | str = 1
    """章节号"""
    map: int | str = 1
    """地图号"""
    fleet_id: int = 1
    """出征舰队"""
    fleet: list[str] | None = None
    """舰队成员名单"""
    repair_mode: RepairMode | list[RepairMode] = RepairMode.severe_damage
    """修理方案"""
    selected_nodes: list[str] = Field(default_factory=list)
    """白名单节点"""
    fight_condition: int = 4
    """战况选择 (1-5)"""

    @model_validator(mode='after')
    def _normalize_repair_mode(self) -> FightConfig:
        """将单个 repair_mode 展开为 6 个位置的列表。"""
        if not isinstance(self.repair_mode, list):
            modes = [self.repair_mode] * 6
            object.__setattr__(self, 'repair_mode', modes)
        return self


class BattleConfig(FightConfig):
    """战役配置。"""

    repair_mode: RepairMode | list[RepairMode] = RepairMode.moderate_damage


class ExerciseConfig(FightConfig):
    """演习配置。"""

    selected_nodes: list[str] = Field(default_factory=lambda: ['player', 'robot'])
    discard: bool = False
    exercise_times: int = 4
    """最大演习次数"""
    robot: bool = True
    """是否打机器人"""
    max_refresh_times: int = 2
    """最大刷新次数"""


# ── ConfigManager ──
# 默认配置文件名（当前目录下）
_DEFAULT_CONFIG_FILENAME = 'usersettings.yaml'


class ConfigManager:
    """配置管理器 — 提供加载入口。"""

    @staticmethod
    def load(path: str | Path | None = None) -> UserConfig:
        """从文件加载用户配置。

        查找策略:

        1. 如果显式指定了 *path*，直接加载该文件；文件不存在时回退默认值。
        2. 如果 *path* 为 ``None``，尝试当前工作目录下的
           ``usersettings.yaml``；文件存在则加载，不存在则使用默认值。

        Parameters
        ----------
        path:
            用户配置文件路径 (YAML)。为 ``None`` 时自动检测。

        Returns
        -------
        UserConfig
            校验后的不可变配置对象。
        """
        if path is not None:
            path = Path(path)
            if not path.exists():
                _log.warning('配置文件 {} 不存在，使用默认配置', path)
                try:
                    return UserConfig()
                except ValidationError:
                    # WSL/Linux 下默认配置缺少 serial/path 无法通过验证，提供占位值
                    return UserConfig(emulator={'serial': '', 'path': ''})
            config = UserConfig.from_yaml(path)
            _log.info('已加载配置: {}', path)
            return config

        # 未指定路径 → 尝试当前目录下的默认配置
        default = Path.cwd() / _DEFAULT_CONFIG_FILENAME
        if default.exists():
            _log.info('检测到默认配置文件: {}', default)
            config = UserConfig.from_yaml(default)
            _log.info('已加载配置: {}', default)
            return config

        _log.info('未指定配置文件且未检测到 {}，使用内置默认配置', _DEFAULT_CONFIG_FILENAME)
        return UserConfig()
