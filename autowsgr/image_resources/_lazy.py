"""延迟加载图像模板描述符与工具函数。"""

from __future__ import annotations

from pathlib import Path

from autowsgr.vision import ImageTemplate

# ═══════════════════════════════════════════════════════════════════════════════
# 资源根目录 — autowsgr/data/images/
# ═══════════════════════════════════════════════════════════════════════════════

IMG_ROOT: Path = Path(__file__).resolve().parent.parent / "data" / "images"


def load_template(relative_path: str, *, name: str | None = None) -> ImageTemplate:
    """从 ``autowsgr/data/images/`` 加载图像模板。

    Parameters
    ----------
    relative_path:
        相对于 ``autowsgr/data/images/`` 的路径。
    name:
        模板名称。默认使用文件名（不含扩展名）。
    """
    return ImageTemplate.from_file(IMG_ROOT / relative_path, name=name)


class LazyTemplate:
    """延迟加载的图像模板描述符。

    首次访问时读取 PNG 文件并缓存结果，后续访问直接返回。

    用法::

        class MyTemplates:
            BTN = LazyTemplate("ui/btn.png", "button")
    """

    def __init__(self, relative_path: str, name: str | None = None) -> None:
        self._path = relative_path
        self._name = name
        self._template: ImageTemplate | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr_name = name
        if self._name is None:
            self._name = name.lower()

    def __get__(self, obj: object, objtype: type | None = None) -> ImageTemplate:
        if self._template is None:
            self._template = load_template(self._path, name=self._name)
        return self._template

    def __repr__(self) -> str:
        return f"LazyTemplate({self._path!r}, name={self._name!r})"
