"""文件 / YAML 工具函数。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml


def _get_package_data_dir() -> Path:
    """获取 ``autowsgr`` 包安装目录下的 ``data`` 文件夹路径。

    兼容 pip 安装（site-packages）和开发模式（editable install / 源码目录）。
    """
    spec = importlib.util.find_spec('autowsgr')
    if spec is None or spec.origin is None:
        raise RuntimeError('无法定位 autowsgr 包安装路径')
    return Path(spec.origin).resolve().parent / 'data'


def resolve_plan_path(
    name_or_path: str | Path,
    category: str = 'normal_fight',
) -> Path:
    """解析策略文件路径。

    查找优先级:

    1. *name_or_path* 直接作为路径（绝对路径或相对于 cwd），若存在即使用。
    2. 同上，补全 ``.yaml`` 后缀再试。
    3. 在 ``autowsgr/data/plan/{category}/`` 包数据目录中查找。
    4. 同上，补全 ``.yaml`` 后缀再试。

    支持 pip 安装模式和开发模式。

    Parameters
    ----------
    name_or_path:
        策略文件名（如 ``"7-4千伪"``）或完整路径。
    category:
        策略分类子目录，如 ``"normal_fight"``、``"event"``。

    Returns
    -------
    Path
        解析后的绝对路径。

    Raises
    ------
    FileNotFoundError
        所有候选路径均不存在。
    """
    p = Path(name_or_path)

    # 1. 直接路径
    if p.exists():
        return p.resolve()

    # 2. 补全 .yaml
    if not p.suffix:
        p_yaml = p.with_suffix('.yaml')
        if p_yaml.exists():
            return p_yaml.resolve()

    # 3. 包数据目录
    data_dir = _get_package_data_dir() / 'plan' / category
    candidate = data_dir / p.name
    if candidate.exists():
        return candidate.resolve()

    # 4. 包数据目录 + .yaml
    if not candidate.suffix:
        candidate_yaml = candidate.with_suffix('.yaml')
        if candidate_yaml.exists():
            return candidate_yaml.resolve()

    raise FileNotFoundError(f'策略文件未找到: {name_or_path!r}\n已搜索: {p} | {data_dir / p.name}')


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
        raise FileNotFoundError(f'YAML 文件不存在: {path}')
    with open(path, encoding='utf-8') as f:
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
    with open(path, 'w', encoding='utf-8') as f:
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
