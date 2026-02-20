"""安卓模拟器自动检测与 serial 解析。

流程
----
1. 运行 ``adb devices`` 获取当前在线设备列表。
2. 按 serial 端口规则推断模拟器类型。
3. 结合 :class:`~autowsgr.infra.config.EmulatorConfig` 决定使用哪个 serial：

   - ``config.serial`` 非空 → 直接使用
   - 仅 1 个在线设备      → 自动选择
   - 多个在线设备且能按 ``config.type`` 唯一匹配 → 自动选择
   - 其余                  → 命令行提示用户选择（非 TTY 则抛出异常）

公开接口
--------
.. code-block:: python

    from autowsgr.emulator.detector import detect_emulators, resolve_serial

    # 仅探测
    candidates = detect_emulators()

    # 结合配置自动决策（ADBController 内部调用）
    from autowsgr.infra.config import EmulatorConfig
    serial = resolve_serial(EmulatorConfig())
"""

from __future__ import annotations

import re
import shutil
import subprocess
import os
import winreg
import sys
from dataclasses import dataclass, field

from loguru import logger

from autowsgr.infra import EmulatorConnectionError
from autowsgr.types import EmulatorType
from autowsgr.infra import EmulatorConfig


# ── serial → EmulatorType 识别规则 ──
# 每条规则：(正则, 模拟器类型)
# 按顺序匹配，首条命中即止。
_SERIAL_RULES: list[tuple[re.Pattern[str], EmulatorType]] = [
    # 雷电：emulator-5554, emulator-5556 …
    (re.compile(r"^emulator-\d+$"), EmulatorType.leidian),
    # MuMu 12（新版）：127.0.0.1:16384, 16416, 16448 … 步进 32
    (re.compile(r"^127\.0\.0\.1:(1638[4-9]|16[4-9]\d{2}|1[7-9]\d{3})$"), EmulatorType.mumu),
    # MuMu 旧版：127.0.0.1:62001, 62025, 62049 …
    (re.compile(r"^127\.0\.0\.1:620\d{2}$"), EmulatorType.mumu),
    # 蓝叠：127.0.0.1:5555, 5565, 5575 … 步进 10
    (re.compile(r"^127\.0\.0\.1:5(5[5-9]\d|[6-9]\d{2})\d?$"), EmulatorType.bluestacks),
    # 蓝叠也用这些端口段
    (re.compile(r"^127\.0\.0\.1:555[5-9]$"), EmulatorType.bluestacks),
]


@dataclass
class EmulatorCandidate:
    """ADB 探测到的单个设备候选。

    Attributes
    ----------
    serial:
        ADB serial 地址，例如 ``"127.0.0.1:16384"``、``"emulator-5554"``。
    emulator_type:
        推断出的模拟器类型；无法识别时为 ``None``。
    status:
        ADB 返回的设备状态，通常为 ``"device"``、``"offline"`` 或 ``"unauthorized"``。
    description:
        向用户展示的友好描述字符串。
    """

    serial: str
    emulator_type: EmulatorType | None
    status: str
    description: str = field(init=False)

    def __post_init__(self) -> None:
        type_label = self.emulator_type.value if self.emulator_type else "未知"
        self.description = f"{self.serial:<25} {type_label:<8} ({self.status})"


# ── ADB 可执行文件解析 ──

def _registry_adb_candidates_windows() -> list[str]:
    """从 Windows 注册表中读取各模拟器安装目录，返回可能的 adb 路径列表。

    仅读取注册表，不做路径存在性判断（由调用方统一检查）。
    找不到对应注册表键时静默跳过，不抛出异常。
    """
    candidates: list[str] = []

    # ── 雷电模拟器 ──
    # HKLM\SOFTWARE\leidian\<子键>\InstallDir
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\leidian") as key:
            sub_key_name = winreg.EnumKey(key, 0)
            with winreg.OpenKey(key, sub_key_name) as sub:
                install_dir, _ = winreg.QueryValueEx(sub, "InstallDir")
                candidates.append(os.path.join(install_dir, "adb.exe"))
    except OSError as exc:
        logger.debug("[Detector] 雷电模拟器注册表读取跳过: {}", exc)

    # ── 蓝叠（国内版） ──
    # HKLM\SOFTWARE\BlueStacks_nxt_cn\InstallDir
    for reg_key in (r"SOFTWARE\BlueStacks_nxt_cn", r"SOFTWARE\BlueStacks_nxt"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key) as key:
                install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                candidates.append(os.path.join(install_dir, "HD-Adb.exe"))
                break
        except OSError as exc:
            logger.debug("[Detector] 蓝叠模拟器注册表读取跳过 ({}): {}", reg_key, exc)

    # ── MuMu 12（新版） ──
    # HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MuMuPlayer-12.0
    # UninstallString 指向卸载程序，其 dirname 为安装根目录
    # adb 位于 <root>\shell\adb.exe
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MuMuPlayer-12.0",
        ) as key:
            uninstall_str, _ = winreg.QueryValueEx(key, "UninstallString")
            root = os.path.dirname(uninstall_str.strip('"'))
            candidates.append(os.path.join(root, "shell", "adb.exe"))
    except OSError as exc:
        logger.debug("[Detector] MuMu 12 注册表读取跳过: {}", exc)

    # ── MuMu 旧版 ──
    # UninstallString dirname → <root>\nx_main\adb.exe
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MuMuPlayer",
        ) as key:
            uninstall_str, _ = winreg.QueryValueEx(key, "UninstallString")
            root = os.path.dirname(uninstall_str.strip('"'))
            candidates.append(os.path.join(root, "nx_main", "adb.exe"))
    except OSError as exc:
        logger.debug("[Detector] MuMu 旧版注册表读取跳过: {}", exc)

    return candidates


def _find_adb() -> str:
    """返回 adb 可执行文件路径。

    搜索顺序：
    1. 系统 PATH（``adb`` 命令）
    2. Windows：从注册表读取各模拟器安装目录，构造 adb 路径并验证存在性

    Raises
    ------
    FileNotFoundError
        找不到 adb 可执行文件。
    """
    if path := shutil.which("adb"):
        return path

    if sys.platform.startswith("win"):
        for candidate in _registry_adb_candidates_windows():
            if os.path.isfile(candidate):
                logger.debug("[Detector] 从注册表找到 adb: {}", candidate)
                return candidate

    raise FileNotFoundError(
        "未找到 adb 可执行文件。请将 adb 加入系统 PATH，"
        "或在配置文件中手动指定 emulator.serial。"
    )


# ── 核心探测函数 ──

def list_adb_devices(adb_path: str | None = None) -> list[tuple[str, str]]:
    """运行 ``adb devices`` 并解析结果。

    Parameters
    ----------
    adb_path:
        adb 可执行文件路径；``None`` 时自动查找。

    Returns
    -------
    list[tuple[str, str]]
        ``(serial, status)`` 列表，**不含** ``List of devices attached`` 首行。
    """
    adb = adb_path or _find_adb()
    try:
        result = subprocess.run(
            [adb, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise EmulatorConnectionError("adb devices 超时，请检查 adb 是否正常运行") from exc
    except FileNotFoundError as exc:
        raise EmulatorConnectionError(f"adb 可执行文件未找到: {adb}") from exc

    lines = result.stdout.strip().splitlines()
    devices: list[tuple[str, str]] = []
    for line in lines[1:]:  # 跳过第一行 "List of devices attached"
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append((parts[0], parts[1]))
    return devices


def identify_emulator_type(serial: str) -> EmulatorType | None:
    """根据 serial 格式推断模拟器类型。

    Parameters
    ----------
    serial:
        ADB serial 字符串。

    Returns
    -------
    EmulatorType | None
        识别成功返回对应类型；无法识别返回 ``None``。
    """
    for pattern, emu_type in _SERIAL_RULES:
        if pattern.match(serial):
            return emu_type
    return None


def detect_emulators(adb_path: str | None = None) -> list[EmulatorCandidate]:
    """探测当前所有在线（status == 'device'）的 Android 设备。

    Parameters
    ----------
    adb_path:
        adb 可执行文件路径；``None`` 时自动查找。

    Returns
    -------
    list[EmulatorCandidate]
        仅包含 status 为 ``"device"`` 的候选设备，按 serial 排序。
    """
    raw = list_adb_devices(adb_path)
    candidates: list[EmulatorCandidate] = []
    for serial, status in raw:
        emu_type = identify_emulator_type(serial)
        cand = EmulatorCandidate(serial=serial, emulator_type=emu_type, status=status)
        if status == "device":
            candidates.append(cand)
        else:
            logger.debug("[Detector] 忽略非在线设备: {}", cand.description)

    logger.debug("[Detector] 检测到 {} 个在线设备", len(candidates))
    return sorted(candidates, key=lambda c: c.serial)


# ── 用户交互选择 ──

def prompt_user_select(candidates: list[EmulatorCandidate]) -> str:
    """命令行交互，让用户从多个设备中选择一个。

    Parameters
    ----------
    candidates:
        至少包含 2 个候选设备的列表。

    Returns
    -------
    str
        用户选择的 serial。

    Raises
    ------
    EmulatorConnectionError
        当前不是 TTY（脚本/管道环境），无法交互。
    """
    if not sys.stdin.isatty():
        serials = ", ".join(c.serial for c in candidates)
        raise EmulatorConnectionError(
            f"检测到多个在线设备（{serials}），无法自动选择。\n"
            "请在配置文件中设置 emulator.serial 以指定目标设备。"
        )

    print("\n检测到多个在线设备，请选择要连接的模拟器：\n")
    for i, cand in enumerate(candidates):
        print(f"  [{i}] {cand.description}")
    print()

    while True:
        try:
            raw = input(f"请输入编号 [0-{len(candidates) - 1}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise EmulatorConnectionError("用户取消了设备选择") from None

        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(candidates):
                chosen = candidates[idx]
                logger.info("[Detector] 用户选择设备: {}", chosen.description)
                return chosen.serial

        print(f"  无效输入，请输入 0 到 {len(candidates) - 1} 之间的整数。")


# ── 主入口：结合配置决策 ──

def resolve_serial(config: EmulatorConfig, adb_path: str | None = None) -> str:
    """根据配置和当前在线设备决定最终连接的 serial。

    决策优先级（从高到低）：

    1. ``config.serial`` 非空 → 直接返回
    2. 在线设备恰好 1 个     → 自动采用
    3. 在线设备多于 1 个，``config.type`` 恰好匹配 1 个 → 自动采用
    4. 在线设备多于 1 个，无法唯一匹配 → :func:`prompt_user_select`
    5. 没有在线设备 → 抛出 :class:`~autowsgr.infra.exceptions.EmulatorConnectionError`

    Parameters
    ----------
    config:
        :class:`~autowsgr.infra.config.EmulatorConfig` 实例。
    adb_path:
        adb 可执行文件路径；``None`` 时自动查找。

    Returns
    -------
    str
        最终决定使用的 ADB serial。

    Raises
    ------
    EmulatorConnectionError
        无在线设备，或多设备时无法确定且非 TTY 环境。
    """
    # 优先级 1：用户显式配置
    if config.serial:
        logger.debug("[Detector] 使用配置中的 serial: {}", config.serial)
        return config.serial

    # 探测在线设备
    try:
        candidates = detect_emulators(adb_path)
    except FileNotFoundError as exc:
        raise EmulatorConnectionError(str(exc)) from exc

    # 优先级 5：无设备
    if not candidates:
        raise EmulatorConnectionError(
            "未检测到任何在线 Android 设备。\n"
            "请确认模拟器已启动，或在配置文件中手动设置 emulator.serial。"
        )

    # 优先级 2：唯一设备
    if len(candidates) == 1:
        serial = candidates[0].serial
        logger.info(
            "[Detector] 自动选择唯一在线设备: {}",
            candidates[0].description,
        )
        return serial

    # 优先级 3：多设备，按 config.type 过滤
    if config.type:
        matched = [c for c in candidates if c.emulator_type == config.type]
        if len(matched) == 1:
            serial = matched[0].serial
            logger.info(
                "[Detector] 按模拟器类型 '{}' 自动选择: {}",
                config.type.value,
                matched[0].description,
            )
            return serial
        if len(matched) > 1:
            logger.warning(
                "[Detector] 模拟器类型 '{}' 匹配到 {} 个设备，需要用户选择",
                config.type.value,
                len(matched),
            )
            return prompt_user_select(matched)

    # 优先级 4：无法唯一确定，交互选择
    logger.warning("[Detector] 检测到 {} 个在线设备，需要用户选择", len(candidates))
    return prompt_user_select(candidates)
