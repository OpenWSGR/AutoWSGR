import os
from functools import cmp_to_key, partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np
import yaml
from PIL.Image import Image


def listdir(path):
    """返回指定目录下所有文件路径的列表(含 path 前缀)
    Args:
        path (_type_): _description_

    Returns:
        _type_: _description_
    """
    return [os.path.join(path, file) for file in os.listdir(path)]


def all_in(elements, set):
    return all(element in set for element in elements)


def yaml_to_dict(yaml_file):
    """将yaml文件转换为字典"""
    # 处理yaml文件中的转义字符\
    with open(yaml_file, encoding='utf-8') as f:
        content = f.read()
    content = content.replace('\\', '\\\\')
    return yaml.load(content, Loader=yaml.FullLoader)  # noqa: S506


def dict_to_yaml(dict_data, yaml_file):
    """将字典转换为yaml文件"""
    with open(yaml_file, 'w') as f:
        yaml.dump(dict_data, f)


def recursive_dict_update(d, u, skip=None):
    if skip is None:
        skip = []
    for k, v in u.items():
        if k in skip:
            continue
        if isinstance(v, dict):
            r = recursive_dict_update(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


def create_nested_dict(directory: str) -> dict:
    """
    创建一个嵌套字典，表示目录及其子目录中的文件
    Args:
        directory (str): 目录路径
    Returns:
        dict: 嵌套字典，表示目录结构
    """
    ret = {}
    for root, _dirs, files in os.walk(directory):
        # 获取相对于根目录的路径
        rel_path = os.path.relpath(root, directory)
        # 获取当前层级的字典
        current_dict = ret
        if rel_path != '.':
            for part in rel_path.split(os.sep):
                current_dict = current_dict.setdefault(part, {})
        # 将文件添加到当前层级的字典中
        for file in files:
            file_key = os.path.splitext(file)[0]
            # 赋予其绝对路径
            current_dict[file_key] = os.path.abspath(os.path.join(root, file))
    return ret


def get_file_suffix_name(path):
    """返回文件后缀名,不包含 '.'

    For Example:
        >>> get_file_suffix_name("testdir\\testfile.py")
        'py'
    Args:
        path (str): 文件路径

    Raises:
        FileNotFoundError: 不存在该文件
        ValueError: 'path' 是目录而不是文件

    Returns:
        str: 表示后缀名
    """
    if not os.path.exists(path):
        raise FileNotFoundError('file ' + os.path.abspath(path) + ' not found')
    if os.path.isdir(path):
        raise ValueError("arg 'path' is not a file but a dir")
    file = os.path.basename(path)
    return os.path.splitext(file)[-1][1:]


def read_file(path):
    """给定文件路径,返回

    Args:
        timer (Timer): _description_
        path (_type_): _description_

    Raises:
        FileNotFoundError: _description_

    Returns:
        _type_: _description_
    """
    if not os.path.exists(path):
        raise FileNotFoundError('file ' + os.path.abspath(path) + ' not found')
    with open(path) as f:
        return f.read()


def create_file_with_path(path):
    """给定一个不存在文件的相对路径并创建路径和该文件
    Args:
        path (str):需要创建的文件路径
    """
    dirname = os.path.dirname(path)
    if dirname != '':
        os.makedirs(dirname, exist_ok=True)
    if not os.path.exists(path):
        with open(path, 'w') as _f:
            pass


def delete_file(path):
    if os.path.exists(path):
        os.remove(path)


def cv_imread(file_path):
    """读取含中文路径的图片, 返回一个字节流对象"""
    with open(file_path, 'rb') as file:
        return file.read()  # 读取整个文件的字节流


def save_image(path, image, ignore_existed_image=False, *args, **kwargs):
    """未测试"""
    """保存一张图片到给定路径

    Args:
        path (str):包含图片名的图片路径
        ignore_existed_image (bool, optional):是否忽略已存在图片. Defaults to False.

    Raises:
        FileExistsError: 如果未忽略已存在图片并且图片已存在
    """
    if not ignore_existed_image and os.path.exists(path):
        raise FileExistsError('该图片已存在')
    if isinstance(image, Image):
        image.save(os.path.abspath(path))
    if isinstance(image, np.ndarray):
        cv2.imencode('.png', image)[1].tofile(path)


def get_all_files(dir):
    return [os.path.join(r, file) for r, _d, f in os.walk(dir) for file in f]


def count(keys, iter):
    return sum(1 for it in iter if (it in keys))


class MyNamespace(SimpleNamespace):
    def __getitem__(self, key) -> Any:
        return getattr(self, key)

    def __setitem__(self, key, value) -> None:
        setattr(self, key, value)


def namespace_to_dict(namespace):
    """将 SimpleNamespace 对象递归转化为字典."""
    if not isinstance(namespace, SimpleNamespace):
        return namespace
    return {key: namespace_to_dict(value) for key, value in namespace.__dict__.items()}


def create_namespace(directory: str, template: partial) -> MyNamespace:
    """
    根据文件夹层次结构创建 SimpleNamespace 对象.

    Args:
        directory (str): 要遍历的根目录.
        template (type): 用于创建 file 对象的模板.

    Returns:
        SimpleNamespace: 包含文件路径的 SimpleNamespace 对象.
    """

    def compare_length_and_alphabet(a, b):
        """
        比较函数, 先比较字符串长度, 长的排在后面,
        如果长度相同, 则比较字母序
        """
        if len(a.stem) == len(b.stem):
            return 0 if a.stem == b.stem else (-1 if a.stem < b.stem else 1)
        if len(a.stem) < len(b.stem):
            return -1
        return 1

    root = Path(directory)
    namespace = MyNamespace()

    for path in sorted(
        root.rglob('*.[pP][nN][gG]'),
        key=cmp_to_key(compare_length_and_alphabet),
    ):
        *parts, folder, filename = path.parts
        current = namespace
        for part in parts[len(root.parts) :]:
            if not hasattr(current, part):
                setattr(current, part, MyNamespace())
            current = getattr(current, part)

        filename = Path(filename).stem
        if filename.isdigit():
            # 1. 一个文件夹内全是数字的情况
            if not hasattr(current, folder):
                setattr(current, folder, [None])  # 占位符
            getattr(current, folder).append(template(path))
        else:
            if not hasattr(current, folder):
                setattr(current, folder, MyNamespace())
            current = getattr(current, folder)
            if filename != filename.rstrip(r'0123456789'):
                # 2. 以数字后缀结尾的文件名情况，代表多个等价图片
                filename = filename.rstrip(r'0123456789')
                if not hasattr(current, filename):
                    setattr(current, filename, [])
                getattr(current, filename).append(template(path))
            else:
                # 3. 字符串文件情况
                setattr(current, filename, template(path))

    # pprint(namespace_to_dict(namespace))
    return namespace
