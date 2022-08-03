
from cv2 import imwrite
from supports.models import *
__all__ = ['get_file_suffixname', 'read_file', 'create_file_with_path',
           'delete_file', 'write_file', 'save_image', 'get_all_files']


def get_file_suffixname(path):
    """返回文件后缀名,不包含 '.'

    For Example:
        >>> get_file_suffixname("testdir\\testfile.py")
        'py'
    Args:
        path (str): 文件路径

    Raises:
        FileNotFoundError: 不存在该文件
        ValueError: 'path' 是目录而不是文件

    Returns:
        str: 表示后缀名
    """
    if(os.path.exists(path) == False):
        raise FileNotFoundError("file " + os.path.abspath(path) + " not found")
    if(os.path.isdir(path)):
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
    if(os.path.exists(path) == False):
        raise FileNotFoundError("file " + os.path.abspath(path) + "not found")
    with open(path, mode='r') as f:
        return f.read()


def create_file_with_path(path):
    """给定一个不存在文件的相对路径并创建路径和该文件
    Args:
        path (str):需要创建的文件路径 
    """
    dirname = os.path.dirname(path)
    if(dirname != ''):
        os.makedirs(dirname, exist_ok=True)
    if(os.path.exists(path) == False):
        file = open(path, 'w')
        file.close()


def delete_file(path):
    os.system("del " + path)


def write_file(path, info):
    """给定文件的路径和需要添加的信息，向文件中添加写入信息。

    Args:
        path (str): 文件路径
        info (str): 需要添加的信息 
    """
    if(os.path.exists(path) == False):
        create_file_with_path(path)
    with open(path, mode='a') as f:
        f.write(info)


def save_image(path, image, ignore_existed_image=False, *args, **kwargs):
    """未测试"""
    """保存一张图片到给定路径

    Args:
        path (str):包含图片名的图片路径
        ignore_existed_image (bool, optional):是否忽略已存在图片. Defaults to False.

    Raises:
        FileExistsError: 如果未忽略已存在图片并且图片已存在
    """
    if(ignore_existed_image == False and os.path.exists(path)):
        raise FileExistsError("该图片已存在")
    if(isinstance(image, PIM.Image)):
        image.save(os.path.abspath(path))
    if(isinstance(image, np.ndarray)):
        imwrite(path, image)


def get_all_files(dir, must='/'):
    files = os.listdir(dir)
    res = []
    for x in files:
        if(os.path.isdir(dir + "/" + x)):
            res += get_all_files(dir + "/" + x, must)
            continue
        if(must not in dir + "/" + x):
            continue
        res.append(dir + "/" + x)
    return res
