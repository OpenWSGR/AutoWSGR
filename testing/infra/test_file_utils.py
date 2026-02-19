"""测试文件工具函数。"""

from pathlib import Path

import pytest

from autowsgr.infra.file_utils import load_yaml, merge_dicts, save_yaml


class TestLoadYaml:
    """测试 load_yaml。"""

    def test_load_simple(self, tmp_yaml):
        p = tmp_yaml("test.yaml", "key: value\ncount: 42\n")
        result = load_yaml(p)
        assert result == {"key": "value", "count": 42}

    def test_load_nested(self, tmp_yaml):
        content = "a:\n  b:\n    c: 1\n"
        p = tmp_yaml("nested.yaml", content)
        result = load_yaml(p)
        assert result == {"a": {"b": {"c": 1}}}

    def test_load_empty_file(self, tmp_yaml):
        p = tmp_yaml("empty.yaml", "")
        result = load_yaml(p)
        assert result == {}

    def test_load_list(self, tmp_yaml):
        content = "items:\n  - a\n  - b\n  - c\n"
        p = tmp_yaml("list.yaml", content)
        result = load_yaml(p)
        assert result == {"items": ["a", "b", "c"]}

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_yaml(Path("nonexistent_file.yaml"))

    def test_chinese_content(self, tmp_yaml):
        content = "name: 胡德\ntype: 战巡\n"
        p = tmp_yaml("cn.yaml", content)
        result = load_yaml(p)
        assert result == {"name": "胡德", "type": "战巡"}


class TestSaveYaml:
    """测试 save_yaml。"""

    def test_save_and_reload(self, tmp_path: Path):
        data = {"key": "value", "nested": {"a": 1}}
        path = tmp_path / "output.yaml"
        save_yaml(data, path)
        assert path.exists()
        reloaded = load_yaml(path)
        assert reloaded == data

    def test_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "dir" / "config.yaml"
        save_yaml({"k": "v"}, path)
        assert path.exists()

    def test_chinese_roundtrip(self, tmp_path: Path):
        data = {"舰船": ["胡德", "俾斯麦"], "类型": "战巡"}
        path = tmp_path / "cn_out.yaml"
        save_yaml(data, path)
        reloaded = load_yaml(path)
        assert reloaded == data


class TestMergeDicts:
    """测试 merge_dicts。"""

    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = merge_dicts(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge(self):
        base = {"a": {"x": 1, "y": 2}, "b": 10}
        override = {"a": {"y": 99, "z": 3}}
        result = merge_dicts(base, override)
        assert result == {"a": {"x": 1, "y": 99, "z": 3}, "b": 10}

    def test_override_dict_with_scalar(self):
        base = {"a": {"x": 1}}
        override = {"a": "flat_value"}
        result = merge_dicts(base, override)
        assert result == {"a": "flat_value"}

    def test_does_not_mutate_originals(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        merge_dicts(base, override)
        assert base == {"a": {"x": 1}}
        assert override == {"a": {"y": 2}}
