"""文件 / YAML 工具函数。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    """加载 YAML 文件并返回字典。

    Parameters
    ----------
    path:
        YAML 文件路径。

    Returns
    -------
    dict[str, Any]
        解析后的字典，空文件返回 ``{}``。

    Raises
    ------
    FileNotFoundError
        文件不存在。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"YAML 文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(data: dict[str, Any], path: str | Path) -> None:
    """将字典保存为 YAML 文件。

    Parameters
    ----------
    data:
        要保存的字典数据。
    path:
        目标文件路径，父目录会自动创建。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def merge_dicts(base: dict, override: dict) -> dict:
    """深度合并两个字典，*override* 中的值优先。

    Parameters
    ----------
    base:
        基础字典。
    override:
        覆盖字典。

    Returns
    -------
    dict
        合并后的新字典（不修改原字典）。
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
