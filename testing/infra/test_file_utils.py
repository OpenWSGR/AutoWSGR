"""测试文件工具函数。"""

from collections.abc import Callable
from pathlib import Path

import pytest

from autowsgr.infra import load_yaml, merge_dicts, save_yaml
from autowsgr.infra.file_utils import resolve_plan_path


class TestLoadYaml:
    """测试 load_yaml。"""

    def test_load_simple(self, tmp_yaml: Callable[[str, str], Path]):
        p = tmp_yaml('test.yaml', 'key: value\ncount: 42\n')
        result = load_yaml(p)
        assert result == {'key': 'value', 'count': 42}

    def test_load_nested(self, tmp_yaml: Callable[[str, str], Path]):
        content = 'a:\n  b:\n    c: 1\n'
        p = tmp_yaml('nested.yaml', content)
        result = load_yaml(p)
        assert result == {'a': {'b': {'c': 1}}}

    def test_load_empty_file(self, tmp_yaml: Callable[[str, str], Path]):
        p = tmp_yaml('empty.yaml', '')
        result = load_yaml(p)
        assert result == {}

    def test_load_list(self, tmp_yaml: Callable[[str, str], Path]):
        content = 'items:\n  - a\n  - b\n  - c\n'
        p = tmp_yaml('list.yaml', content)
        result = load_yaml(p)
        assert result == {'items': ['a', 'b', 'c']}

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_yaml(Path('nonexistent_file.yaml'))

    def test_chinese_content(self, tmp_yaml: Callable[[str, str], Path]):
        content = 'name: 胡德\ntype: 战巡\n'
        p = tmp_yaml('cn.yaml', content)
        result = load_yaml(p)
        assert result == {'name': '胡德', 'type': '战巡'}


class TestSaveYaml:
    """测试 save_yaml。"""

    def test_save_and_reload(self, tmp_path: Path):
        data = {'key': 'value', 'nested': {'a': 1}}
        path = tmp_path / 'output.yaml'
        save_yaml(data, path)
        assert path.exists()
        reloaded = load_yaml(path)
        assert reloaded == data

    def test_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / 'deep' / 'nested' / 'dir' / 'config.yaml'
        save_yaml({'k': 'v'}, path)
        assert path.exists()

    def test_chinese_roundtrip(self, tmp_path: Path):
        data = {'舰船': ['胡德', '俾斯麦'], '类型': '战巡'}
        path = tmp_path / 'cn_out.yaml'
        save_yaml(data, path)
        reloaded = load_yaml(path)
        assert reloaded == data


class TestMergeDicts:
    """测试 merge_dicts。"""

    def test_simple_merge(self):
        base = {'a': 1, 'b': 2}
        override = {'b': 3, 'c': 4}
        result = merge_dicts(base, override)
        assert result == {'a': 1, 'b': 3, 'c': 4}

    def test_deep_merge(self):
        base = {'a': {'x': 1, 'y': 2}, 'b': 10}
        override = {'a': {'y': 99, 'z': 3}}
        result = merge_dicts(base, override)
        assert result == {'a': {'x': 1, 'y': 99, 'z': 3}, 'b': 10}

    def test_override_dict_with_scalar(self):
        base = {'a': {'x': 1}}
        override = {'a': 'flat_value'}
        result = merge_dicts(base, override)
        assert result == {'a': 'flat_value'}

    def test_does_not_mutate_originals(self):
        base = {'a': {'x': 1}}
        override = {'a': {'y': 2}}
        merge_dicts(base, override)
        assert base == {'a': {'x': 1}}
        assert override == {'a': {'y': 2}}


class TestResolvePlanPath:
    """测试 resolve_plan_path —— 含 plan_root 优先 / 回退语义。

    对齐 classic ``plan_root``: 用户自定义目录同名文件优先于包内默认,
    未命中则回退到 ``autowsgr/data/plan/{category}/``。
    """

    def test_plan_root_overrides_package_default(self, tmp_path: Path):
        """plan_root 同名文件优先于包内默认。"""
        root = tmp_path / 'my_plans'
        (root / 'normal_fight').mkdir(parents=True)
        user_plan = root / 'normal_fight' / '1-1.yaml'
        user_plan.write_text('# user override\n', encoding='utf-8')

        resolved = resolve_plan_path('1-1', plan_root=root)
        assert resolved == user_plan.resolve()

    def test_plan_root_without_yaml_suffix(self, tmp_path: Path):
        """plan_root 查找支持省略 .yaml 后缀。"""
        root = tmp_path / 'my_plans'
        (root / 'normal_fight').mkdir(parents=True)
        (root / 'normal_fight' / 'custom.yaml').write_text('k: v\n', encoding='utf-8')

        resolved = resolve_plan_path('custom', plan_root=root)
        assert resolved.name == 'custom.yaml'
        assert resolved.parent == (root / 'normal_fight').resolve()

    def test_fallback_to_package_default(self, tmp_path: Path):
        """plan_root 未命中时回退到包内默认目录。"""
        from autowsgr.infra.file_utils import _get_package_data_dir

        root = tmp_path / 'empty_plans'
        (root / 'normal_fight').mkdir(parents=True)

        resolved = resolve_plan_path('1-1', plan_root=root)
        expected_dir = (_get_package_data_dir() / 'plan' / 'normal_fight').resolve()
        assert resolved.parent == expected_dir
        assert resolved.name == '1-1.yaml'

    def test_no_plan_root_falls_back_to_package(self):
        """plan_root=None 时仅查包内默认 (旧行为不变)。"""
        from autowsgr.infra.file_utils import _get_package_data_dir

        resolved = resolve_plan_path('1-1')
        expected_dir = (_get_package_data_dir() / 'plan' / 'normal_fight').resolve()
        assert resolved.parent == expected_dir

    def test_not_found_lists_searched_paths(self, tmp_path: Path):
        """都不存在时抛 FileNotFoundError 并列出所有搜索过的路径。"""
        root = tmp_path / 'my_plans'
        (root / 'normal_fight').mkdir(parents=True)

        with pytest.raises(FileNotFoundError) as exc_info:
            resolve_plan_path('绝对不存在的策略', plan_root=root)

        msg = str(exc_info.value)
        assert '绝对不存在的策略' in msg
        # 错误信息应同时包含 plan_root 候选与包数据目录候选
        assert str(root / 'normal_fight') in msg
