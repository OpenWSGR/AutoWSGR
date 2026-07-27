"""向下兼容层 — 检测 classic 老版本配置项 (运行期崩溃) + 迁移 (独立工具)。

两类**纯 API**, 均无副作用 (不写文件、不改运行期全局):

- :func:`detect_legacy_user_config` / :func:`detect_legacy_plan`:
  运行期 ``from_yaml`` 调用。只读, 返回命中的老版本项描述列表; 非空则
  ``from_yaml`` 抛 :class:`LegacyConfigError`, 提示用户运行迁移工具升级。
- :func:`migrate_raw_config` / :func:`migrate_plan_dict`:
  迁移工具 (``tools/migrate_config.py``) 调用。原地把 raw dict 转成 dev
  格式, 由工具负责把结果写到新输出目录 (原文件不动)。

检测 / 迁移的老版本项 (运行期一律**不再自动处理**, 必须先迁移):

- ``ship_name_file`` (新版无需自定义舰船名文件) — 删除
- ``account.account`` / ``account.password`` (自动登录已移除) — 删除
- ``delay`` (classic 单值秒数) → ``operation_delay_min`` / ``operation_delay_max``
- ``emulator_type`` / ``emulator_start_cmd`` / ``emulator_name`` (顶层平铺)
  → 嵌套 ``emulator`` 块 (``type`` / ``path`` / ``serial``)
- ``check_update`` / ``show_map_node`` (顶层废弃) — 删除
- 计划文件 ``fleet`` 前导空占位 (classic 1-indexed) → dev 0-indexed
"""

from __future__ import annotations

from typing import Any

from autowsgr.infra.logger import get_logger


_log = get_logger('infra')


class LegacyConfigError(Exception):
    """配置含 classic 老版本字段, 需先运行迁移工具 (``tools/migrate_config.py``)。"""


# ── 常量 / 辅助 (detect 与 migrate 共享, 单一事实源) ──

# classic 平铺模拟器字段 (顶层) → dev 嵌套 emulator 块键名
_LEGACY_EMULATOR_FIELDS: dict[str, str] = {
    'emulator_type': 'type',
    'emulator_start_cmd': 'path',
    'emulator_name': 'serial',
}

# classic 顶层废弃字段 (dev 不使用, 子模型 extra='ignore' 会静默丢弃)
_LEGACY_TOPLEVEL_DROPPED: tuple[str, ...] = (
    'check_update',
    'show_map_node',
)


def _is_empty_fleet_slot(value: object) -> bool:
    """是否是 fleet 的"空槽位" (``None`` / 空串 / 纯空白)。

    与 :func:`autowsgr.ui.battle.fleet_change._normalize_ship_name` 的
    空判定一致: 这些值在运行期都会被归一化为 ``None`` (该槽位留空)。
    """
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


# ── 检测 (运行期, 只读) ──


def detect_legacy_user_config(data: Any) -> list[str]:
    """返回 *data* 中命中的老版本用户配置项描述; 空列表 = 干净。

    运行期 :meth:`UserConfig.from_yaml <autowsgr.infra.config.UserConfig.from_yaml>`
    调用: 非空即抛 :class:`LegacyConfigError`。纯只读, 不修改 *data*。
    """
    if not isinstance(data, dict):
        return []
    found: list[str] = []
    if 'ship_name_file' in data:
        found.append('ship_name_file (新版无需自定义舰船名文件)')
    account = data.get('account')
    if isinstance(account, dict) and any(k in account for k in ('account', 'password')):
        found.append('account.account / account.password (自动登录已移除)')
    if 'delay' in data:
        found.append('delay (请改用 operation_delay_min / operation_delay_max)')
    if any(k in data for k in _LEGACY_EMULATOR_FIELDS):
        found.append(
            'classic 平铺模拟器字段 emulator_type / emulator_start_cmd / '
            'emulator_name (请改用嵌套 emulator 块)',
        )
    if any(k in data for k in _LEGACY_TOPLEVEL_DROPPED):
        found.append(
            '、'.join(k for k in _LEGACY_TOPLEVEL_DROPPED if k in data) + ' (顶层废弃)',
        )
    return found


def detect_legacy_plan(data: Any) -> list[str]:
    """返回 *data* 中命中的老版本计划项描述; 空列表 = 干净。

    运行期 :meth:`CombatPlan.from_yaml <autowsgr.combat.plan.CombatPlan.from_yaml>`
    调用: 非空即抛 :class:`LegacyConfigError`。纯只读, 不修改 *data*。
    """
    if not isinstance(data, dict):
        return []
    fleet = data.get('fleet')
    if isinstance(fleet, list) and fleet and _is_empty_fleet_slot(fleet[0]):
        return ['classic 1-indexed fleet 前导空占位 (首位为空, 请剥离)']
    return []


# ── 迁移 (工具, 原地转换) ──


def migrate_raw_config(data: Any) -> Any:
    """原地转换 raw 用户配置 dict 为 dev 格式并返回同一对象。

    迁移工具调用; 与 :func:`detect_legacy_user_config` 对应。无副作用:
    不写文件、不改运行期全局 (``operation_delay`` 全局由
    :class:`~autowsgr.infra.config.UserConfig` 字段 + 校验器接管)。
    """
    if not isinstance(data, dict):
        return data
    _migrate_ship_name_file(data)
    _migrate_account(data)
    _migrate_delay(data)
    _migrate_emulator_legacy(data)
    _migrate_misc_legacy(data)
    return data


def migrate_plan_dict(data: Any) -> Any:
    """原地转换 raw 计划 dict 为 dev 格式并返回同一对象。

    目前处理 classic 的 1-indexed ``fleet`` 前导空占位
    (见 :func:`_migrate_plan_fleet`)。迁移工具调用, 无副作用。
    """
    if not isinstance(data, dict):
        return data
    _migrate_plan_fleet(data)
    return data


# ── 迁移子函数 (原地改 data) ──


def _migrate_ship_name_file(data: dict[str, Any]) -> None:
    """ship_name_file: 新版无需自定义舰船名文件, 删除并提示。"""
    if 'ship_name_file' in data:
        _log.warning('[compat] ship_name_file 已废弃 (新版无需), 已从配置移除。')
        del data['ship_name_file']


def _migrate_account(data: dict[str, Any]) -> None:
    """account.account / password: 自动登录已移除, 删除并提示 (保留 game_app)。"""
    account = data.get('account')
    if not isinstance(account, dict):
        return
    removed = [k for k in ('account', 'password') if k in account]
    if not removed:
        return
    _log.warning(
        '[compat] 自动登录已移除, account 块中的 {} 已删除 (保留 game_app)。',
        '/'.join(removed),
    )
    for key in removed:
        del account[key]


def _migrate_delay(data: dict[str, Any]) -> None:
    """delay: classic 单值秒数 → operation_delay_min = operation_delay_max = delay。

    纯字段赋值 (由 :class:`~autowsgr.infra.config.UserConfig` 校验器
    ``_apply_operation_delay`` 把字段值写回运行期全局); 不在此设全局。
    """
    if 'delay' not in data:
        return
    raw = data.pop('delay')
    try:
        delay = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        _log.warning(
            '[compat] delay={!r} 无法解析为数值, 已忽略; '
            '如需 UI 操作延迟请设置 operation_delay_min/max。',
            raw,
        )
        return
    # 仅在用户未显式设置 operation_delay_min/max 时回填, 避免覆盖已部分迁移的显式值
    data.setdefault('operation_delay_min', delay)
    data.setdefault('operation_delay_max', delay)
    _log.info('[compat] delay={} 已迁移为 operation_delay_min/max。', delay)


def _migrate_emulator_legacy(data: dict[str, Any]) -> None:
    """classic 平铺模拟器字段 → 嵌套 ``emulator`` 块。

    classic 把模拟器配置平铺在顶层 (``emulator_type`` /
    ``emulator_start_cmd`` / ``emulator_name``); dev 改为嵌套
    ``emulator:`` 块 (``type`` / ``path`` / ``serial``)。本函数把平铺
    字段搬进嵌套块, 让老配置直接生效 (否则顶层字段被 ``extra='ignore'``
    静默丢弃, 模拟器会回退到默认雷电)。

    值原样透传, 由 :class:`~autowsgr.infra.config.EmulatorConfig` 校验 /
    解析 (如 ``"MuMu"`` → ``EmulatorType.mumu``)。``None`` 值不写, 让
    dev 自动检测。若已含嵌套 ``emulator`` 块, 以嵌套为准, 平铺仅补缺。
    """
    found = {legacy: data[legacy] for legacy in _LEGACY_EMULATOR_FIELDS if legacy in data}
    if not found:
        return

    emu = data.get('emulator')
    if emu is None:
        emu = {}
        data['emulator'] = emu
    if not isinstance(emu, dict):
        _log.warning(
            '[compat] 检测到 classic 平铺模拟器字段 {} 但 emulator 块非 dict, '
            '无法自动迁移, 平铺字段已删除。',
            '/'.join(found),
        )
        for legacy in found:
            del data[legacy]
        return

    migrated: list[str] = []
    for legacy, new_key in _LEGACY_EMULATOR_FIELDS.items():
        if legacy not in found:
            continue
        del data[legacy]
        value = found[legacy]
        if value is None or new_key in emu:
            continue  # 空值让 dev 自动检测; 嵌套已有则以嵌套为准
        emu[new_key] = value
        migrated.append(f'{legacy}→emulator.{new_key}')

    _log.warning(
        '[compat] classic 平铺模拟器字段已迁移到嵌套 emulator 块 ({}){}。',
        ', '.join(migrated) if migrated else '仅清理空值',
        '' if migrated else ', 未写入新值',
    )


def _migrate_misc_legacy(data: dict[str, Any]) -> None:
    """classic 顶层已废弃字段 (check_update / 顶层 show_map_node 等) 删除并提示。"""
    dropped = [k for k in _LEGACY_TOPLEVEL_DROPPED if k in data]
    if not dropped:
        return
    for key in dropped:
        del data[key]
    _log.warning('[compat] classic 顶层字段 {} 已废弃 (新版不使用), 已删除。', '/'.join(dropped))


def _migrate_plan_fleet(data: dict[str, Any]) -> None:
    r"""classic 1-indexed ``fleet`` → dev 0-indexed: 剥离前导空占位元素。

    classic 计划的 ``fleet`` 是 1-indexed, 首位恒为 ``""`` 占位, 例如::

        fleet: ["", "吹雪", "明斯克", "胡德", "赤诚", ""]

    dev 的 :meth:`~autowsgr.ui.battle.fleet_change.FleetChangeMixin.change_fleet`
    按 0-indexed 取前 6 个, 前导空占位会把舰船整体右移一位、丢掉第 6 船,
    并触发 ``_reorder`` 的 ``break`` 致验证反复重试 ("卡很多次 fleet 验证")。
    本函数剥离所有前导"空槽位", 让经典写法直接生效。

    中间 / 尾部的 ``""`` 原样保留 —— 运行期 ``_normalize_ship_name`` 会把
    它们归一化为 ``None`` (= 不关心该槽位), 无需在此处理。
    """
    fleet = data.get('fleet')
    if not isinstance(fleet, list) or not fleet:
        return

    cleaned = list(fleet)
    while cleaned and _is_empty_fleet_slot(cleaned[0]):
        cleaned.pop(0)

    if cleaned != fleet:
        data['fleet'] = cleaned
        _log.warning(
            '[compat] classic 1-indexed fleet 前导空占位已剥离 ({} → {}), '
            '已迁移为 dev 0-indexed 格式。',
            fleet,
            cleaned,
        )
