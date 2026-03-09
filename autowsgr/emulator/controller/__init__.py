"""Android 设备控制器 — 模拟器层核心。

提供纯粹的设备操作能力（截图、点击、滑动、按键、应用管理），
**不做**任何图像识别、页面判定或游戏逻辑。

所有触控坐标使用 **相对值** (0.0-1.0)：

- 左上角 = (0.0, 0.0)
- 右下角趋近 (1.0, 1.0)
- 内部自动根据实际分辨率转换为像素坐标

使用方式::

    from autowsgr.emulator.controller import ADBController

    ctrl = ADBController(serial="emulator-5554")
    info = ctrl.connect()
    screen = ctrl.screenshot()
    ctrl.click(0.5, 0.5)
    ctrl.disconnect()
"""

from .protocol import AndroidController, DeviceInfo
from .scrcpy import ScrcpyController


__all__ = [
    'AndroidController',
    'DeviceInfo',
    'ScrcpyController',
]
