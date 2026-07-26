"""向下兼容层 — 集中处理用户 YAML 中的废弃 / 迁移字段。

所有 classic 遗留配置的迁移、删除提示、自动映射都集中在本模块,
不分散到各子模型。在 :func:`UserConfig.from_yaml` 的
``model_validate`` 之前对 raw dict 做一次性预处理。

设计要点
--------
- 迁移 / 删除在内存 raw dict 上原地完成; 若调用方传入 ``source_path``
  且检测到改动, 会把迁移后的配置**写回原文件**, 使迁移一次性生效、后续
  不再重复告警。回写的是 raw dict (``model_validate`` 之前), 故**只含
  用户已定义字段**, 不会把 Pydantic 默认值灌进用户文件。
- 删除的字段因子模型默认 ``extra='ignore'`` 不会报错; 本模块额外**主动提示**
  用户删除, 避免旧字段在配置里造成误导。
- ``delay`` (classic 单值秒数) 自动映射到模块全局
  :data:`~autowsgr.infra.config.OPERATION_DELAY_MIN` /
  :data:`~autowsgr.infra.config.OPERATION_DELAY_MAX`,
  由 :func:`~autowsgr.infra.config.operation_delay` 运行期读取。
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from autowsgr.infra import config as _config
from autowsgr.infra.file_utils import save_yaml
from autowsgr.infra.logger import get_logger


if TYPE_CHECKING:
    from pathlib import Path


_log = get_logger('infra')


def migrate_raw_config(
    data: dict[str, Any],
    *,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    """预处理用户 raw 配置 dict: 迁移 / 删除废弃字段并提示。

    在 ``UserConfig.model_validate`` 之前调用。原地修改并返回同一对象。
    集中处理 classic 遗留字段, 见模块文档字符串。

    若给出 *source_path* 且检测到 dict 发生改动, 会把迁移后的 dict 写回
    该文件 (best-effort: 写回失败仅告警, 不影响本次加载), 使迁移一次性
    生效、后续运行不再重复告警。回写的是 raw dict, 不含 Pydantic 默认值。
    """
    if not isinstance(data, dict):
        return data

    before = copy.deepcopy(data)

    _migrate_ship_name_file(data)
    _migrate_account(data)
    _migrate_delay(data)
    _migrate_emulator_legacy(data)
    _migrate_misc_legacy(data)

    if source_path is not None and data != before:
        _persist(data, source_path)

    return data


def _persist(data: dict[str, Any], source_path: str | Path) -> None:
    """把迁移后的 raw dict 写回 *source_path* (best-effort)。

    只在迁移确有改动时调用。写回失败不抛异常 —— 迁移已在内存生效,
    本次加载不受影响; 仅告警提示用户手动整理配置文件。
    """
    try:
        save_yaml(data, source_path)
    except Exception as e:  # 写回是 best-effort 副作用, 不得阻断配置加载
        _log.warning(
            '[compat] 迁移后写回配置文件失败 ({}): {!r}; 本次按内存迁移结果继续, '
            '请手动按新版格式整理配置文件。',
            source_path,
            e,
        )
        return
    _log.info('[compat] 迁移后的配置已写回 {}', source_path)


def _migrate_ship_name_file(data: dict[str, Any]) -> None:
    """ship_name_file: 新版无需自定义舰船名文件, 删除并提示。"""
    if 'ship_name_file' in data:
        _log.warning(
            '[compat] ship_name_file 已废弃 (新版无需自定义舰船名文件), 已从配置移除。',
        )
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
        '[compat] 自动登录已移除, account 块中的 {} 已废弃, 已从配置移除 (保留 game_app)。',
        '/'.join(removed),
    )
    for key in removed:
        del account[key]


def _migrate_delay(data: dict[str, Any]) -> None:
    """delay: classic 单值延迟, 自动映射为 OPERATION_DELAY_MIN = MAX = delay。"""
    if 'delay' not in data:
        return
    raw = data.pop('delay')
    try:
        delay = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        _log.warning(
            '[compat] delay={!r} 无法解析为数值, 已忽略; '
            '如需 UI 操作延迟请直接设置 OPERATION_DELAY_MIN/MAX。',
            raw,
        )
        return
    _config.OPERATION_DELAY_MIN = delay
    _config.OPERATION_DELAY_MAX = delay
    _log.warning(
        '[compat] delay={} 已自动映射为 OPERATION_DELAY_MIN/MAX。'
        '该字段已从配置移除, 后续请直接设置 OPERATION_DELAY。',
        delay,
    )


# classic 平铺模拟器字段 (顶层) → dev 嵌套 emulator 块键名
_LEGACY_EMULATOR_FIELDS: dict[str, str] = {
    'emulator_type': 'type',
    'emulator_start_cmd': 'path',
    'emulator_name': 'serial',
}


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


# classic 顶层废弃字段 (dev 不使用, 子模型 extra='ignore' 会静默丢弃)
_LEGACY_TOPLEVEL_DROPPED: tuple[str, ...] = (
    'check_update',
    'show_map_node',
)


def _migrate_misc_legacy(data: dict[str, Any]) -> None:
    """classic 顶层已废弃字段 (check_update / 顶层 show_map_node 等) 删除并提示。"""
    dropped = [k for k in _LEGACY_TOPLEVEL_DROPPED if k in data]
    if not dropped:
        return
    for key in dropped:
        del data[key]
    _log.warning(
        '[compat] classic 顶层字段 {} 已废弃 (新版不使用), 已删除。',
        '/'.join(dropped),
    )
