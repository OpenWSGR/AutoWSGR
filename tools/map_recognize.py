import os
import pathlib
import sys


sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import cv2
import keyboard
from numpy.typing import NDArray

from autowsgr.timer import Timer
from autowsgr.utils.io import dict_to_yaml, listdir
from autowsgr.utils.math_functions import cal_dis


# ============ 颜色检测常量 ============
COLOR_CHECK_RADIUS = 1  # 检查颜色一致性的半径（像素）
COLOR_DISTANCE_THRESHOLD = 10  # 颜色距离阈值（用于判断是否为不同颜色）

# ============ UI 相关常量 ============
CROSSHAIR_SIZE = 15  # 十字指示物的臂长（像素）


class LightweightTimer(Timer):
    """轻量级 Timer，仅用于截图功能，跳过不必要的模块加载"""

    def __init__(self, config, logger) -> None:
        # 只初始化必要的属性
        self.config = config
        self.logger = logger

        # 初始化日志相关的基础属性
        self.everyday_check = True
        self.ship_stats = [0, 0, 0, 0, 0, 0, 0]
        self.enemy_type_count = {}
        self.now_page = None
        self.resources = None
        self.got_ship_num = 0
        self.got_loot_num = 0
        self.quick_repaired_cost = 0
        self.can_get_loot = False

        # 跳过 initialize_resources()、initialize_controllers()、initialize_ocr() 和 init()
        # 直接调用父类的 AndroidController 初始化以获得截图功能
        self.initialize_controllers()


# en_reader = easyocr.Reader(['en'], gpu=False)
timer = None
point = 'A'
screen_shot_count = 0


def log_image(event: keyboard.KeyboardEvent):
    global screen_shot_count
    assert isinstance(timer, Timer)
    if event.event_type != 'down' or event.name != 'P':
        return
    print('Screen Processing:', screen_shot_count)
    screen_shot_count += 1
    timer.update_screen()
    timer.log_screen()


def set_points(windowname, img: NDArray):
    """
    输入图片，打开该图片进行标记点，返回的是标记的几个点的字符串和相对坐标
    """
    global point
    point = 'A'
    print('(提示：单击需要标记的坐标，Enter确定，Esc跳过，其它重试。)')
    points = {}
    relative_points = {}

    def on_mouse(event, x, y, flags, param):
        global point
        if event == cv2.EVENT_LBUTTONDOWN:
            cv2.circle(temp_img, (x, y), 10, (102, 217, 239), -1)
            points[point] = [x, y]
            relative_points[point] = [x / img.shape[1], y / img.shape[0]]
            point = chr(ord(point) + 1)
            cv2.imshow(windowname, temp_img)

    temp_img = img.copy()
    cv2.namedWindow(windowname)
    cv2.imshow(windowname, temp_img)
    cv2.setMouseCallback(windowname, on_mouse)
    key = cv2.waitKey(0)
    if key == 13:  # Enter
        print('坐标为：', points)
        print('相对坐标为：', relative_points)
        del temp_img
        cv2.destroyAllWindows()
        str(points)
    elif key == 27:  # ESC
        print('跳过该张图片')
        del temp_img
        cv2.destroyAllWindows()
    else:
        print('重试!')
        set_points(windowname, img)

    print(points)
    print(relative_points)
    return points, relative_points


def draw_crosshair(img, x, y, color, size=CROSSHAIR_SIZE):
    """绘制十字型指示物，中间镂空，其他地方与图片反色

    Args:
        img: 图片数组
        x, y: 十字中心坐标
        color: BGR 格式的反色颜色
        size: 十字臂长
    """
    # 水平线
    cv2.line(img, (x - size, y), (x - 5, y), color, 2)
    cv2.line(img, (x + 5, y), (x + size, y), color, 2)
    # 竖直线
    cv2.line(img, (x, y - size), (x, y - 5), color, 2)
    cv2.line(img, (x, y + 5), (x, y + size), color, 2)


def get_inverted_color(img, x, y):
    """获取图片中某点的反色

    Args:
        img: BGR 格式的图片数组
        x, y: 坐标

    Returns:
        反色的 BGR 元组（整数）
    """
    b, g, r = img[y, x]
    return (int(255 - b), int(255 - g), int(255 - r))


def check_color_uniformity(
    img, x, y, radius=COLOR_CHECK_RADIUS, threshold=COLOR_DISTANCE_THRESHOLD
):
    """检查指定点周围是否有其他颜色的像素

    Args:
        img: BGR 格式的图片数组
        x, y: 中心坐标
        radius: 检查半径（像素）
        threshold: 颜色距离阈值

    Returns:
        (is_uniform, different_color_positions) - 是否一致，以及不一致的像素位置列表
    """
    # 转换为 Python int 列表，避免 np.uint8 类型导致的计算错误
    center_color = [int(c) for c in img[y, x]]
    different_positions = []

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            ny, nx = y + dy, x + dx
            # 检查边界
            if 0 <= nx < img.shape[1] and 0 <= ny < img.shape[0]:
                # 转换为 Python int 列表
                pixel_color = [int(c) for c in img[ny, nx]]
                # 使用欧氏距离计算颜色差异（cal_dis 返回的是距离的平方）
                dist_squared = cal_dis(center_color, pixel_color)
                print(dist_squared, center_color, pixel_color)
                if dist_squared > threshold**2:  # 将阈值平方进行比较
                    different_positions.append((nx, ny))

    return len(different_positions) == 0, different_positions


def set_points_with_color(windowname, img: NDArray, color_threshold=COLOR_DISTANCE_THRESHOLD):
    """
    选择点并记录颜色，类似于 make_map，但记录 BGR 颜色值
    返回的是标记的几个点的列表，每个点为 [x, y, [B, G, R]]
    周围{COLOR_CHECK_RADIUS}像素内如果有其他颜色，会用反色方框标记并提示是否撤销
    """
    print('(提示：单击需要标记的坐标，Enter确定，Esc跳过，其它重试。)')
    print(
        f'(颜色检测：如果周围{COLOR_CHECK_RADIUS}像素内有其他颜色的像素，会用反色标记并提示是否撤销。)'
    )
    print('(缩放：使用鼠标滚轮放大/缩小，按 R 键重置为原始大小。)')
    points = []

    # 原始尺寸的显示图像（用于标记）
    display_img = img.copy()

    # 缩放相关变量
    scale_factor = [1.0]  # 使用列表便于在嵌套函数中修改
    scaled_display_img = [display_img.copy()]  # 保存缩放后的显示图像

    def update_and_show_scaled_image():
        """根据当前 display_img 和缩放因子显示图像"""
        if scale_factor[0] == 1.0:
            scaled_display_img[0] = display_img.copy()
            cv2.imshow(windowname, display_img)
        else:
            h, w = display_img.shape[:2]
            new_w = int(w * scale_factor[0])
            new_h = int(h * scale_factor[0])
            # 使用最近邻插值以保持像素精确性
            scaled_display_img[0] = cv2.resize(
                display_img, (new_w, new_h), interpolation=cv2.INTER_NEAREST
            )
            cv2.imshow(windowname, scaled_display_img[0])

    def highlight_different_colors(event, x, y, flags, param):
        # 处理缩放后的坐标转换回原始图像坐标
        actual_x = int(x / scale_factor[0])
        actual_y = int(y / scale_factor[0])

        # 检查坐标是否在原始图像范围内
        if actual_x < 0 or actual_x >= img.shape[1] or actual_y < 0 or actual_y >= img.shape[0]:
            return

        if event == cv2.EVENT_LBUTTONDOWN:
            # 从原始图像获取该点的颜色（确保取色准确，转换为 Python int 列表）
            pixel_color = [int(c) for c in img[actual_y, actual_x]]

            # 检查周围是否有其他颜色
            is_uniform, diff_positions = check_color_uniformity(
                img, actual_x, actual_y, threshold=color_threshold
            )

            if not is_uniform:
                # 对检测到的每个不同颜色的像素进行逐像素反色
                for diff_x, diff_y in diff_positions:
                    display_img[diff_y, diff_x] = get_inverted_color(display_img, diff_x, diff_y)

                # 先显示标记，让用户看到问题位置
                update_and_show_scaled_image()
                cv2.waitKey(100)  # 让 OpenCV 有时间更新显示

                # 显示警告信息
                print('\n警告：周围像素内检测到其他颜色！')
                print(f'中心颜色: {pixel_color}')
                print(f'检测到 {len(diff_positions)} 个不同颜色的像素')

                # 等待用户输入
                response = input('是否撤销这个点？(y/n): ').lower()

                # 无论是否撤销，都立即擦除反色标记（对每个像素反色两次回到原色）
                for diff_x, diff_y in diff_positions:
                    display_img[diff_y, diff_x] = get_inverted_color(display_img, diff_x, diff_y)

                update_and_show_scaled_image()

                if response == 'y':
                    print('已撤销这个点')
                    return

            # 保存点信息：坐标和颜色
            points.append([[actual_x, actual_y], pixel_color])

            # 仅反色中心像素作为标记
            display_img[actual_y, actual_x] = get_inverted_color(display_img, actual_x, actual_y)

            update_and_show_scaled_image()
            print(
                f'已标记第 {len(points)} 个点，坐标: ({actual_x}, {actual_y})，颜色: {pixel_color}'
            )

        elif event == cv2.EVENT_MOUSEWHEEL:
            # 鼠标滚轮事件：正数为向上滚（放大），负数为向下滚（缩小）
            if flags > 0:  # 放大
                scale_factor[0] = min(scale_factor[0] * 1.1, 5.0)  # 最大放大 5 倍
            else:  # 缩小
                scale_factor[0] = max(scale_factor[0] / 1.1, 0.2)  # 最小缩小到 0.2 倍
            update_and_show_scaled_image()

    cv2.namedWindow(windowname)
    update_and_show_scaled_image()
    cv2.setMouseCallback(windowname, highlight_different_colors)

    print('(按 R 键重置图像大小为原始大小)')

    while True:
        key = cv2.waitKey(0)
        if key == 13:  # Enter
            print(f'\n标记完成，共标记 {len(points)} 个点')
            print('坐标和颜色为：', points)
            del display_img
            cv2.destroyAllWindows()
            break
        elif key == 27:  # ESC
            print('跳过该张图片')
            del display_img
            cv2.destroyAllWindows()
            break
        elif key == ord('r') or key == ord('R'):  # R 键重置大小
            scale_factor[0] = 1.0
            update_and_show_scaled_image()
            print('已重置为原始大小')

    return points


def get_image() -> None:
    global timer
    # 使用轻量级 Timer 而不是完整的 Timer
    from autowsgr.configs import UserConfig
    from autowsgr.utils.io import yaml_to_dict
    from autowsgr.utils.logger import Logger

    config_dict = yaml_to_dict('../examples/user_settings.yaml')
    config = UserConfig.from_dict(config_dict)
    logger = Logger(config.log_dir, config.log_level)
    timer = LightweightTimer(config, logger)

    import time

    keyboard.hook(log_image)
    time.sleep(1000)


def make_map(image_path: str, dict_dir: str) -> None:
    """根据图像目录下的所有图片文件,打开后顺次点击ABCD,生成对应文件名的地图文件

    Args:
        image_path (_type_): _description_
        dict_dir (_type_): _description_
    """
    files = listdir(image_path)
    for file in files:
        f = pathlib.Path(file)
        if f.suffix != '.PNG':
            continue
        name = f.stem
        dict_value, relative_value = set_points(name, cv2.imread(file))
        dict_to_yaml(dict_value, os.path.join(dict_dir, 'E-' + name[1:] + '.yaml'))
        dict_to_yaml(dict_value, os.path.join(dict_dir, 'H-' + name[1:] + '.yaml'))
        dict_to_yaml(
            relative_value,
            os.path.join(dict_dir, 'E-' + name[1:] + '_relative.yaml'),
        )


if __name__ == '__main__':
    print(
        """Input operation type:
          1: log image when 'P' pressed.
          2: make map .yaml files
          3: pick points with color""",
    )
    oper = input().split()[0]
    if oper == '1':
        get_image()
    elif oper == '2':
        print('Enter image_path:')
        image_path = input()
        print('Enter dict_path')
        dict_path = input()
        make_map(image_path, dict_path)
    elif oper == '3':
        print('Enter image_path:')
        image_path = input()
        print('Enter output_path (for .yaml file):')
        output_path = input()
        files = listdir(image_path)
        for file in files:
            f = pathlib.Path(file)
            if f.suffix not in ['.PNG', '.png']:
                continue
            name = f.stem
            img = cv2.imread(file)
            points_with_color = set_points_with_color(name, img)
            if points_with_color:
                dict_to_yaml(points_with_color, os.path.join(output_path, name + '_colors.yaml'))
                print(f'已保存: {os.path.join(output_path, name + "_colors.yaml")}')
