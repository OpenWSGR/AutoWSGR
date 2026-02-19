"""测试公共 fixtures。"""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """测试数据目录。"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_yaml(tmp_path: Path):
    """创建临时 YAML 文件的工厂 fixture。"""

    def _factory(name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    return _factory
