from constants.ui import load_game_ui
from constants.ui import Node
from constants.other_constants import INFO2, INFO1, ALL_UI
from constants.image_templates import BackImage, GameUI, IdentifyImages
from constants.custom_expections import ImageNotFoundErr
from .run_timer import WaitImages, GetImagePosition, is_bad_network, process_bad_network, ImagesExist
from .run_timer import Timer, PixelChecker
from utils.logger import logit

import constants.settings as S
import time

@logit()
def intergrative_page_identify(timer: Timer):
    positions = [(171, 47), (300, 47), (393, 47), (504, 47), (659, 47)]
    for i, position in enumerate(positions):
        if (PixelChecker(timer, position, (225, 130, 16))):
            return i + 1


@logit()
def identify_page(timer: Timer, name, need_screen_shot=True):
    if need_screen_shot:
        timer.UpdateScreen()

    if (name == 'main_page') and (identify_page(timer, 'options_page', 0)):
        return False
    if (name == 'map_page') and ((intergrative_page_identify(timer) != 1 or PixelChecker(timer, (35, 297), (47, 253, 226)))):
        return False
    if (name == 'build_page') and (intergrative_page_identify(timer) != 1):
        return False
    if (name == 'develop_page') and (intergrative_page_identify(timer) != 3):
        return False

    return any(ImagesExist(timer, template, 0) for template in IdentifyImages[name])


@logit()
def wait_pages(timer: Timer, names, timeout=5, gap=.1, after_wait=0.1):
    start_time = time.time()
    if (isinstance(names, str)):
        names = [names]
    while (True):
        timer.UpdateScreen()
        for i, name in enumerate(names):
            if(identify_page(timer, name, 0)):
                time.sleep(after_wait)
                return i + 1

        if (time.time() - start_time > timeout):
            break
        time.sleep(gap)

    raise TimeoutError("identify timeout of" + str(names))


@logit(level=INFO1)
def get_now_page(timer: Timer):
    timer.UpdateScreen()
    for page in ALL_UI:
        if (identify_page(timer, page, need_screen_shot=False, no_log=True)):
            return page
    return None


@logit()
def check_now_page(timer: Timer):
    return identify_page(timer, name=timer.now_page.name, no_log=True)


class GameController():
    
    def __init__(self, timer:Timer, get_expedition=True):
        self.timer = timer
        self.get_expedition = get_expedition
        self.ui = load_game_ui()
        self.now_page = self.ui.get_node_by_name('main_page')
    
    def operate(self, end: Node):
        ui_list = self.ui.find_path(self.now_page, end)
        for next in ui_list[1:]:
            edge = self.now_page.find_edge(next)
            opers = edge.operate()
            for oper in opers:
                fun, args = oper
                if(fun == "click"):
                    self.timer.Android.click(*args)
                else:
                    print("==================================")
                    print("unknown function name:", fun)
                    raise BaseException()
                
            if (edge.other_dst is not None):
                dst = wait_pages(names=[self.now_page.name, edge.other_dst.name])
                if (dst == 1):
                    continue
                if S.DEBUG:
                    print(f"Go page {self.now_page.name} but arrive ", edge.other_dst.name)
                self.now_page = self.ui.get_node_by_name([self.now_page.name, edge.other_dst.name][dst - 1])
                if S.DEBUG:
                    print(self.now_page.name)

                self.operate(end)
                return
            else:
                wait_pages(names=[self.now_page.name])
            time.sleep(.25)
    
    def set_page(self, page_name=None, page=None):
        
        if(page_name is None and page is None):
            now_page = get_now_page(self.timer)
            if(now_page == None):
                raise ImageNotFoundErr("Can't identify the page")
            else:
                self.now_page = self.ui.get_node_by_name(now_page)
            
        elif(page is not None):
            if(not isinstance(page, Node)):
                print("==============================")
                print("arg:page must be an controller.ui.Node object")
                raise ValueError
            
            if (self.ui.page_exist(page)):
                self.now_page = page
            
            raise ValueError('give page do not exist')
        
        page = self.ui.get_node_by_name(page_name)
        if (page is None):
            raise ValueError("can't find the page:", page_name)
        self.now_page = page
    
    def walk_to(self, end, try_times=0):
        try:
            if (isinstance(end, Node)):
                self.operate(end)
                wait_pages(end.name)
                return
            if (isinstance(end, str)):
                self.walk_to(self.ui.get_node_by_name(end))

        except TimeoutError as exception:
            if try_times > 3:
                raise TimeoutError("can't access the page")
            if is_bad_network(timeout=0) == False:
                print("wrong path is operated,anyway we find a way to solve,processing")
                print('wrong info is:', exception)
                self.GoMainPage()
                self.walk_to(end, try_times + 1)
            else:
                while True:
                    if process_bad_network("can't walk to the position because a TimeoutError"):
                        try:
                            if not wait_pages(names=self.now_page.name, timeout=1):
                                self.set_page(get_now_page(self.timer))
                        except:
                            try:
                                self.GoMainPage()
                            except:
                                pass
                            else:
                                break
                        else:
                            break
                    else:
                        raise ValueError('unknown error')
                self.walk_to(end)

    @logit(level=INFO2)
    def GoMainPage(self, QuitOperationTime=0, List=[], ExList=[]):
        """回退到游戏主页

        Args:
            timer (Timer): _description_
            QuitOperationTime (int, optional): _description_. Defaults to 0.
            List (list, optional): _description_. Defaults to [].
            ExList (list, optional): _description_. Defaults to [].

        Raises:
            ValueError: _description_
        """
        if (QuitOperationTime > 200):
            raise ValueError("Error,Couldn't go main page")

        self.now_page = self.ui.get_node_by_name('main_page')
        if (len(List) == 0):
            List = BackImage[1:] + ExList
        type = WaitImages(List + [GameUI[3]], 0.8, timeout=0)

        if type is None:
            self.GoMainPage(QuitOperationTime + 1, List, no_log=True)
            return

        if (type >= len(List)):
            type = WaitImages(List, timeout=0)
            if type is None:
                return

        pos = GetImagePosition(List[type], 0, 0.8)
        self.timer.Android.click(pos[0], pos[1])

        NewList = List[1:] + [List[0]]
        self.GoMainPage(QuitOperationTime + 1, NewList, no_log=True)
    
    @logit(level=INFO2)
    def goto_game_page(self, target='main'):
        """到某一个游戏界面

        Args:
            timer (Timer): _description_
            target (str, str): 目标章节名(见 ./constants/other_constants). Defaults to 'main'.
        """
        self.walk_to(target)
        # wait_pages(names=[timer.now_page.name])
        

def GoMainPage(timer:Timer, *args, **kwargs):
    timer.Game.GoMainPage(*args, **kwargs)


def goto_game_page(timer:Timer, *args, **kwargs):
    timer.goto_game_page(*args, **kwargs)