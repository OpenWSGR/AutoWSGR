"""测试公共 fixtures。"""

from collections.abc import Callable
from pathlib import Path

import pytest

from autowsgr.types import OSType


@pytest.fixture(autouse=True)
def _mock_wsl(monkeypatch: pytest.MonkeyPatch):
    """在非 WSL Linux CI runner 上伪装成 WSL，使 OSType.auto() 不抛异常。

    UserConfig.os_type 默认走 OSType.auto()，在非 WSL 的 Linux CI 上会抛
    "暂不支持非 WSL 的 Linux 系统"；测试构造 UserConfig 时不应依赖宿主环境。
    """
    monkeypatch.setattr(OSType, '_is_wsl', staticmethod(lambda: True))


@pytest.fixture
def fixtures_dir() -> Path:
    """测试数据目录。"""
    return Path(__file__).parent / 'fixtures'


@pytest.fixture
def tmp_yaml(tmp_path: Path) -> Callable[[str, str], Path]:
    """创建临时 YAML 文件的工厂 fixture。"""

    def _factory(name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text(content, encoding='utf-8')
        return p

    return _factory
