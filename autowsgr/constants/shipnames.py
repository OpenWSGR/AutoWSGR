import os

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


SHIPNAMES: list[str] = process_dict(
    load_yaml(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'shipnames.yaml'))
)

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
    existing = set(SHIPNAMES)
    to_add = [n for n in extra if n not in existing]
    if to_add:
        SHIPNAMES[:0] = to_add
