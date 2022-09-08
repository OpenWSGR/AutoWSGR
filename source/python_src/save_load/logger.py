
from api import *
from supports import *


def log_image(timer: Timer, image, name, ndarray_mode="BGR", ignore_existed_image=False, *args, **kwargs):
    """向默认数据记录路径记录图片
    Args:
        image: 图片,PIL.Image.Image 格式或者 numpy.ndarray 格式
        name (str): 图片文件名
    """
    if('png' not in name and 'PNG' not in name):
        name += '.PNG'
    path = os.path.join(timer.log_filepre, name)
    
    save_image(path=path, image=image, ignore_existed_image=ignore_existed_image, *args, **kwargs)


def log_screen(timer: Timer, need_screen_shot=False):
    """向默认数据记录路径记录当前屏幕数据,带时间戳保存
    Args:
        need_screen_shot (bool, optional): 是否新截取一张图片. Defaults to False.
    """
    if(need_screen_shot):
        UpdateScreen(timer)
        
    log_image(timer, image=timer.screen, name=str(time.time())+'screen')


def log_info(timer: Timer, info):
    """向默认信息记录文件记录信息自带换行

    Args:
        info (str): 要记录的信息

    """
    write_file(path=os.path.join(S.LOG_PATH, "log.txt"), info=info+'\n')


def log_debug_info(timer: Timer, info):
    """当调试时向默认信息记录文件记录信息自带换行
    Args:
        info (str): 需要记录的信息
    """
    if(S.DEBUG):
        log_info(timer, info)


if __name__ == '__main__':
    log_info("testinfo")
