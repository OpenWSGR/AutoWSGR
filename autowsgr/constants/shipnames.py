import os
from collections.abc import Mapping

from autowsgr.infra import load_yaml


def process_dict(d: dict) -> list[str]:
    """处理 YAML 数据，提取舰船名称列表。

    预期输入格式为：
    ```yaml
    ships:
      - 舰船A
      - 舰船B
      # ...
    ```

    Parameters
    ----------
    d:
        从 YAML 文件加载的原始数据字典。
    Returns
    -------
        舰船名称列表。
    """
    result = []
    for v in d.values():
        result.extend(v)
    return result


_SHIPNAME_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'data',
    'shipnames.yaml',
)
_BASE_SHIPNAME_GROUPS: dict[str, list[str]] = {
    group_id: list(names) for group_id, names in load_yaml(_SHIPNAME_PATH).items()
}
SHIPNAME_GROUPS: dict[str, list[str]] = {
    group_id: list(names) for group_id, names in _BASE_SHIPNAME_GROUPS.items()
}
_EXTRA_SHIPNAMES: list[str] = []
_SHIPNAME_TO_GROUP: dict[str, str] = {
    name: group_id for group_id, names in SHIPNAME_GROUPS.items() for name in names
}
SHIPNAMES: list[str] = process_dict(SHIPNAME_GROUPS)

# 决战中出现的非舰船名卡片（副官技能等）
DECISIVE_SKILL_NAMES: list[str] = ['长跑训练', '肌肉记忆', '黑科技']


def update_shipnames(extra: list[str]) -> None:
    """将额外名称添加到 :data:`SHIPNAMES` 前端（去重）。

    典型场景：决战开始时把 ``config.level1 + config.level2 + DECISIVE_SKILL_NAMES``
    合并进全局列表，后续 OCR 识别无需再临时拼接候选集。

    Parameters
    ----------
    extra:
        要添加的额外名称列表。
    """
    existing = set(_EXTRA_SHIPNAMES)
    for name in extra:
        if name not in existing:
            _EXTRA_SHIPNAMES.append(name)
            existing.add(name)
    _rebuild_shipnames()


def get_ship_name_group_id(name: str) -> str | None:
    """返回舰名所属的 ``No.xxx`` 舰船组。"""
    group_id = _SHIPNAME_TO_GROUP.get(name)
    return group_id if group_id is not None and group_id.startswith('No.') else None


def get_ship_name_variants(name: str) -> list[str]:
    """返回同一艘船的全部名称，未登记名称只返回自身。"""
    group_id = get_ship_name_group_id(name)
    return list(SHIPNAME_GROUPS[group_id]) if group_id is not None else [name]


def canonical_ship_name(name: str) -> str:
    """将同组名称统一为该舰船组的第一个名称。"""
    return get_ship_name_variants(name)[0]


def ship_name_identity(name: str) -> str:
    """返回用于同船唯一性判断的稳定身份。"""
    return get_ship_name_group_id(name) or name


def expand_ship_name_candidates(candidates: list[str]) -> list[str]:
    """将候选舰名扩展为每个候选所在舰船组的全部名称。"""
    expanded: list[str] = []
    for candidate in candidates:
        for name in get_ship_name_variants(candidate):
            if name not in expanded:
                expanded.append(name)
    return expanded


def set_ship_name_aliases(aliases: Mapping[str, str]) -> None:
    """重置用户自定义名，并追加到目标标准舰名所在的舰船组。"""
    SHIPNAME_GROUPS.clear()
    SHIPNAME_GROUPS.update(
        {group_id: list(names) for group_id, names in _BASE_SHIPNAME_GROUPS.items()},
    )
    _rebuild_shipnames()

    for alias, standard_name in aliases.items():
        group_id = get_ship_name_group_id(standard_name)
        if group_id is not None and alias not in SHIPNAME_GROUPS[group_id]:
            SHIPNAME_GROUPS[group_id].append(alias)
    _rebuild_shipnames()


def _rebuild_shipnames() -> None:
    """原地刷新扁平舰名列表和舰名到分组的索引。"""
    _SHIPNAME_TO_GROUP.clear()
    _SHIPNAME_TO_GROUP.update(
        {name: group_id for group_id, names in SHIPNAME_GROUPS.items() for name in names},
    )
    grouped_names = process_dict(SHIPNAME_GROUPS)
    SHIPNAMES[:] = list(dict.fromkeys([*_EXTRA_SHIPNAMES, *grouped_names]))
