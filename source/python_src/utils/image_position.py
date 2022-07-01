def relative_to_absolute(record_pos, resolution):
    """ 将相对坐标转换为绝对坐标 """
    delta_x, delta_y = record_pos
    _w, _h = resolution
    target_x = delta_x * _w + _w * 0.5
    target_y = delta_y * _w + _h * 0.5
    return target_x, target_y


def absolute_to_relative(absolute_pos, resolution):
    """ 将绝对坐标转换为相对坐标 """
    _w, _h = resolution
    delta_x = (absolute_pos[0] - _w * 0.5) / _w
    delta_y = (absolute_pos[1] - _h * 0.5) / _h
    return delta_x, delta_y


def crop_image(image, pos1, pos2, resolution=(960, 540)):
    """ 按照给定的位置裁剪图片, pos1 左下角, pos2 右上角 """
    x1, y2 = map(int, relative_to_absolute(pos1, resolution))
    x2, y1 = map(int, relative_to_absolute(pos2, resolution))
    return image[y1:y2, x1:x2]
