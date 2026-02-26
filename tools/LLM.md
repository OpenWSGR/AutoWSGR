## 实机调试指南

### 连接与截图

- 通过 Emulator 模块可以连接到模拟器
- 提供了 `save_image` 函数来保存调试截图
- 使用 numpy 提供的函数来处理图像
- 调试完成后，将用到的测试图片保存到 `test_pkg` 中的有关目录，对被调试的函数建立测试防止后期回归

### 快速连接截图 (无需启动游戏)

```python
from autowsgr.scheduler import Launcher

launcher = Launcher('usersettings.yaml')
launcher.load_config()
launcher.connect()
ctx = launcher.build_context()
screen = ctx.ctrl.screenshot()     # numpy RGB (H×W×3)

from autowsgr.infra.logger import save_image
save_image(screen, 'debug', img_dir=Path('logs/debug'))
```

### 调试工具

#### `tools/debug_screenshot.py` — 通用截图 + OCR 调试

```bash
# 截图并检查所有页面签名
python tools/debug_screenshot.py

# 对指定 ROI 区域做 OCR (相对坐标 x1,y1,x2,y2)
python tools/debug_screenshot.py --roi 0.818,0.81,0.875,0.867 --allowlist "0123456789Ex-"

# 从已有图片分析
python tools/debug_screenshot.py -i screenshot.png --roi 0.5,0.5,0.8,0.8

# 查询像素颜色 (相对坐标)
python tools/debug_screenshot.py --pixel 0.5,0.5 --pixel 0.8,0.85

# 检查特定页面签名匹配
python tools/debug_screenshot.py --check-page decisive_battle
```

### OCR 调试常见问题

- **数字被识别为字母** (如 `6` → `G`): 使用 `allowlist` 参数限制候选字符集
  ```python
  result = ocr.recognize_single(cropped, allowlist='0123456789Ex-')
  ```
- **OCR 区域太小**: 先放大 (如 4x nearest-neighbor) 再识别
- **视觉层像素/模板检测失败**: 用 `PixelChecker.check_signature` 的详情 (`details`) 逐像素排查

### 回归测试约定

1. 将调试用到的截图保存到 `test_pkg/<模块名>/` (如 `test_pkg/decisive_ocr/`)
2. 编写 pytest 测试文件 `test_pkg/<模块名>/test_xxx.py`
3. OCR 相关测试使用 `@pytest.fixture(scope="module")` 共享 OCR 引擎实例避免重复初始化
4. 测试应覆盖修复后的正确路径; 可选添加诊断测试记录修复前的错误行为
