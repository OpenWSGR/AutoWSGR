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
    for k, v in d.items():
        result.extend(v)
    return result

SHIPNAMES: list[str] = process_dict(load_yaml(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "shipnames.yaml")))

