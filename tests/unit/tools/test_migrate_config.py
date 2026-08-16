"""tools/migrate_config.py 端到端测试 (无网络/无设备)。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.infra.file_utils import load_yaml

from tools import migrate_config


if TYPE_CHECKING:
    from pathlib import Path


def test_migrate_usersettings_delay_to_operation_delay(tmp_path: Path):
    """classic delay → operation_delay_min/max, 原文件不动。"""
    src = tmp_path / 'usersettings.yaml'
    src.write_text('emulator: {}\ndelay: 1.5\n', encoding='utf-8')
    out = tmp_path / 'out'

    rc = migrate_config.main(['--usersettings', str(src), '--output', str(out)])

    assert rc == 0
    assert (out / 'usersettings.yaml').exists()
    # 原文件不动
    assert 'delay: 1.5' in src.read_text(encoding='utf-8')
    # 迁移后: delay 消失, operation_delay_min/max 各等于 delay
    migrated = load_yaml(out / 'usersettings.yaml')
    assert 'delay' not in migrated
    assert migrated['operation_delay_min'] == 1.5
    assert migrated['operation_delay_max'] == 1.5


def test_migrate_usersettings_emulator_flat_to_nested(tmp_path: Path):
    """classic 平铺模拟器字段 → 嵌套 emulator 块。"""
    src = tmp_path / 'usersettings.yaml'
    src.write_text(
        'emulator_type: "MuMu"\nemulator_start_cmd: "C:/x.exe"\nemulator_name: "127.0.0.1:16384"\n',
        encoding='utf-8',
    )
    out = tmp_path / 'out'

    rc = migrate_config.main(['--usersettings', str(src), '--output', str(out)])

    assert rc == 0
    migrated = load_yaml(out / 'usersettings.yaml')
    assert migrated['emulator'] == {
        'type': 'MuMu',
        'path': 'C:/x.exe',
        'serial': '127.0.0.1:16384',
    }
    assert 'emulator_type' not in migrated


def test_migrate_planroot_mirrors_structure_and_strips_fleet(tmp_path: Path):
    """planroot 递归镜像到 plans/, classic 前导空 fleet 被剥离。"""
    planroot = tmp_path / 'plans'
    (planroot / 'normal_fight').mkdir(parents=True)
    (planroot / 'event').mkdir(parents=True)
    (planroot / 'normal_fight' / 'a.yaml').write_text(
        'fleet: ["", "吹雪", "明斯克"]\n',
        encoding='utf-8',
    )
    (planroot / 'event' / 'b.yaml').write_text(
        'fleet: ["飞龙", "U-1206"]\n',
        encoding='utf-8',
    )
    out = tmp_path / 'out'

    rc = migrate_config.main(['--planroot', str(planroot), '--output', str(out)])

    assert rc == 0
    dst_a = out / 'plans' / 'normal_fight' / 'a.yaml'
    dst_b = out / 'plans' / 'event' / 'b.yaml'
    assert dst_a.exists()
    assert dst_b.exists()
    assert load_yaml(dst_a)['fleet'] == ['吹雪', '明斯克']  # 前导空剥离
    assert load_yaml(dst_b)['fleet'] == ['飞龙', 'U-1206']  # 干净不变


def test_clean_file_copied_as_is_preserves_comments(tmp_path: Path):
    """干净计划文件原样复制 (保留注释, 不经 save_yaml 重排)。"""
    planroot = tmp_path / 'plans'
    planroot.mkdir()
    plan = planroot / 'c.yaml'
    body = '# 注释\nfleet: ["飞龙"]\n'
    plan.write_text(body, encoding='utf-8')
    out = tmp_path / 'out'

    rc = migrate_config.main(['--planroot', str(planroot), '--output', str(out)])

    assert rc == 0
    assert (out / 'plans' / 'c.yaml').read_text(encoding='utf-8') == body


def test_dry_run_writes_nothing(tmp_path: Path):
    src = tmp_path / 'usersettings.yaml'
    src.write_text('delay: 1.0\n', encoding='utf-8')
    out = tmp_path / 'out'

    rc = migrate_config.main(
        ['--usersettings', str(src), '--output', str(out), '--dry-run'],
    )

    assert rc == 0
    assert not out.exists()


def test_existing_nonempty_output_without_force_errors(tmp_path: Path):
    src = tmp_path / 'usersettings.yaml'
    src.write_text('delay: 1.0\n', encoding='utf-8')
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'stale.txt').write_text('x', encoding='utf-8')

    rc = migrate_config.main(['--usersettings', str(src), '--output', str(out)])

    assert rc == 1
    # 原输出目录里的占位文件还在 (未被覆盖)
    assert (out / 'stale.txt').exists()


def test_force_overwrites_existing_output(tmp_path: Path):
    src = tmp_path / 'usersettings.yaml'
    src.write_text('delay: 1.0\n', encoding='utf-8')
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'stale.txt').write_text('x', encoding='utf-8')

    rc = migrate_config.main(
        ['--usersettings', str(src), '--output', str(out), '--force'],
    )

    assert rc == 0
    assert not (out / 'stale.txt').exists()  # 旧目录被清空重建
    assert (out / 'usersettings.yaml').exists()
