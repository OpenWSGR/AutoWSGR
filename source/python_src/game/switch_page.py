
from supports import *
from api import *
from game.identify_pages import *
"""用于切换界面的数据结构和操作
整个游戏 UI 将被构建为一颗以主页为根的有向树,该有向树带横插边
"""

__all__ = ['walk_to', 'GoMainPage', "is_bad_network", 'load_game_ui', 'process_bad_network']

page_count = 0
ui_tree = None
function_tree = None


class SwitchMethod():
    def __init__(self, fun_list):
        self.operates = fun_list

    def operate(self):
        for operation in self.operates:
            operation()

    def print(self):
        for operation in self.operates:
            print(operation, end=" ")


class Node():
    """节点
    保存 UI 树的节点
    """

    def __init__(self, name, id):
        self.id = id
        self.name = name
        self.father_edge = None
        self.father = None
        self.depth = 0
        self.edges = []

    def set_father(self, father):
        self.father = father
        self.father_edge = self.find_edge(father)

    def add_edge(self, edge):
        self.edges.append(edge)

    def find_edges(self, v):
        return [edge for edge in self.edges if edge.v is v]

    def find_edge(self, v):
        from random import choice
        edges = self.find_edges(v)
        if(len(edges) != 0):
            return choice(edges)
        return None

    def print(self):
        print("节点名:", self.name, "节点编号:", self.id)
        print("父节点:", self.father)
        print("节点连边:")
        for edge in self.edges:
            edge.print()

    def __str__(self):
        return self.name


class Edge():
    """图的边
    保存 UI 图的边
    """

    def __init__(self, timer: Timer, operate_fun: SwitchMethod, u: Node, v: Node, other_dst=None, extra_op: SwitchMethod = None):
        self.operate_fun = operate_fun
        self.u = u
        self.v = v
        self.other_dst = other_dst
        self.extra_op = extra_op

    def operate(self, timer: Timer):
        self.operate_fun.operate()
        timer.now_page = self.v

    def print(self,):
        print("起点:", self.u.name, "终点:", self.v.name)


class UI():
    """UI树(拓扑学概念)
    """

    def __init__(self):
        self.nodes = {}

    def add_node(self, node: Node):
        self.nodes[node.name] = node

    def find_path(self, start: Node, end: Node):

        lca = self.lca(start, end)
        path1, path2 = [], []

        while(start != lca):
            path1.append(start)
            start = start.father
        while(end != lca):
            path2.append(end)
            end = end.father
        path2.reverse()
        path = path1 + [lca] + path2
        result, i = [], 0
        while(i < len(path)):
            node = path[i]
            result.append(node)
            if(node.find_edge(path[-1]) != None):
                return result + [path[-1]]
            for j in range(i + 2, len(path)):
                dst = path[j]
                if(node.find_edge(dst) != None):
                    i = j - 1
            i += 1
        return result

    def lca(self, u: Node, v: Node) -> Node:
        if(v.depth > u.depth):
            return self.lca(v, u)
        if(u == v):
            return v
        if(u.depth == v.depth):
            return self.lca(u.father, v.father)
        return self.lca(u.father, v)

    def dfs(self, u: Node):
        for edge in u.edges:
            son = edge.v
            if(son == u.father or son.father != u):
                continue

            son.depth = u.depth + 1
            self.dfs(son)

    def walk_to(self, timer: Timer, end: Node):
        ui_list = self.find_path(timer.now_page, end)
        for next in ui_list[1:]:
            edge = timer.now_page.find_edge(next)
            edge.operate(timer)
            if (edge.other_dst is not None):
                dst = wait_pages(timer, names=[timer.now_page.name, edge.other_dst.name])
                if(dst == 1):
                    continue
                if S.DEBUG:
                    print(f"Go page {timer.now_page.name} but arrive ", edge.other_dst.name)
                timer.now_page = get_node_by_name(timer, [timer.now_page.name, edge.other_dst.name][dst - 1])
                if S.DEBUG:
                    print(timer.now_page.name)

                walk_to(timer, end)
                return
            else:
                wait_pages(timer, names=[timer.now_page.name])
            time.sleep(.25)

    def get_node_by_name(self, name):
        return self.nodes.get(name)

    def print(self):

        for node in self.nodes.values():
            node.print()

    def page_exist(self, page):
        return page in self.nodes.values()


def GoMainPage(timer: Timer, QuitOperationTime=0, List=[], ExList=[]):
    """回退到游戏主页

    Args:
        timer (Timer): _description_
        QuitOperationTime (int, optional): _description_. Defaults to 0.
        List (list, optional): _description_. Defaults to [].
        ExList (list, optional): _description_. Defaults to [].

    Raises:
        ValueError: _description_
    """
    if(QuitOperationTime > 200):
        raise ValueError("Error,Couldn't go main page")

    timer.now_page = get_node_by_name(timer, 'main_page')
    if(len(List) == 0):
        List = BackImage[1:] + ExList
    type = WaitImages(timer, List + [GameUI[3]], 0.8, timeout=0)

    if type is None:
        GoMainPage(timer, QuitOperationTime + 1, List)
    if (type >= len(List)):
        type = WaitImages(timer, List, timeout=0)
        if type is None:
            return

    pos = GetImagePosition(timer, List[type], 0, 0.8)
    click(timer, pos[0], pos[1])

    NewList = List[1:] + [List[0]]
    GoMainPage(timer, QuitOperationTime + 1, NewList)


def list_walk_path(timer: Timer, start: Node, end: Node):
    global ui_tree
    path = ui_tree.find_path(start, end)
    for node in path:
        print(node, end="->")


def is_bad_network(timer: Timer, timeout=10):
    return WaitImages(timer, [error_images['bad_network'][0], SymbolImage[10]], timeout=timeout) != None


def process_bad_network(timer: Timer, extra_info=""):
    """判断并处理网络状况问题

    Args:
        timer (Timer): _description_
        extra_info (_type_): 额外的输出信息

    Returns:
        bool: 如果为 True 则表示为网络状况问题,并已经成功处理,否则表示并非网络问题或者处理超时.
    Raise:
        TimeoutError:处理超时
    """
    start_time = time.time()
    while (is_bad_network(timer)):
        print("bad network at", time.time())
        print('extra info:', extra_info)
        while True:
            if(time.time() - start_time >= 180):
                raise TimeoutError("Process bad network timeout")
            if CheckNetWork() != False:
                break

        start_time2 = time.time()
        while(ImagesExist(timer, [SymbolImage[10]] + error_images['bad_network'])):
            time.sleep(.5)
            if(time.time() - start_time2 >= 60):
                break
            if(ImagesExist(timer, error_images['bad_network'])):
                click(timer, 476, 298, delay=2)

        if(time.time() - start_time2 < 60):
            if(S.DEBUG):
                print("ok network problem solved, at", time.time())
            return True

    return False


def walk_to(timer: Timer, end, try_times=0):
    try:
        if(isinstance(end, Node)):
            timer.ui.walk_to(timer, end)
            wait_pages(timer, end.name)
            return
        if(isinstance(end, str)):
            walk_to(timer, get_node_by_name(timer, end))

    except TimeoutError as exception:
        if try_times > 3:
            raise TimeoutError("can't access the page")
        if is_bad_network(timer, timeout=0) == False:
            print("wrong path is operated,anyway we find a way to solve,processing")
            print('wrong info is:', exception)
            GoMainPage(timer)
            walk_to(timer, end, try_times + 1)
        else:
            while True:
                if process_bad_network(timer, "can't walk to the position because a TimeoutError"):
                    try:
                        if not wait_pages(timer, names=timer.now_page.name, timeout=1):
                            timer.set_page(get_now_page(timer))
                    except:
                        try:
                            GoMainPage(timer)
                        except:
                            pass
                        else:
                            break
                    else:
                        break
                else:
                    raise ValueError('unknown error')
            walk_to(timer, end)


def construct_node(timer: Timer, name: str, father) -> Node:
    global page_count, ui_tree
    page_count += 1
    node = Node(name, page_count)
    node.set_father(father)
    ui_tree.add_node(node)
    return node


def construct_clicks_method(timer: Timer, click_position_args):
    operations = []
    for operation in click_position_args:
        operations.append(lambda oper=operation: click(timer, *oper))
    return SwitchMethod(operations)


def add_edge(timer: Timer, u: Node, v: Node, method: SwitchMethod, other_dst=None):
    edge = Edge(timer, method, u, v, other_dst=other_dst)
    u.add_edge(edge)


def construct_intergrative_pages(timer: Timer, father, click_positions=[], names=[], common_edges=[]):

    assert(len(click_positions) == len(names))
    first_node = construct_node(timer, names[0], father)
    nodes = [first_node]
    for i, name in enumerate(names[1:]):
        nodes.append(construct_node(timer, name, first_node))

    for i, node in enumerate(nodes):
        for j, click_position in enumerate(click_positions):
            if(i == j):
                continue
            add_edge(timer, node, nodes[j], construct_clicks_method(timer, [click_position]))

        for edge in common_edges:
            dst = edge.get('dst')
            x, y = edge.get('pos')
            add_edge(timer, node, dst, construct_clicks_method(timer, [(x, y)]))

    return nodes


def get_node_by_name(timer: Timer, name: str):
    return timer.ui.get_node_by_name(name)


def load_game_ui(timer: Timer):
    global ui_tree, function_tree
    ui_tree = UI()

    main_page = construct_node(timer, 'main_page', None)
    map_page, exercise_page, expedition_page, battle_page, decisive_battle_entrance = \
        construct_intergrative_pages(timer, main_page, names=['map_page', 'exercise_page', 'expedition_page', 'battle_page', 'decisive_battle_entrance'],
                                     click_positions=[(163, 25), (287, 25), (417, 25), (544, 25), (661, 25)],
                                     common_edges=[{'pos': (30, 30), 'dst': main_page}])

    options_page = construct_node(timer, 'options_page', main_page)
    build_page, destroy_page, develop_page, discard_page = \
        construct_intergrative_pages(timer, options_page, names=['build_page', 'destroy_page', 'develop_page', 'discard_page', ],
                                     click_positions=[(163, 25), (287, 25), (417, 25), (544, 25)],
                                     common_edges=[{'pos': (30, 30), 'dst': options_page}])
    intensify_page, remake_page, skill_page = \
        construct_intergrative_pages(timer, options_page, names=['intensify_page', 'remake_page', 'skill_page', ],
                                     click_positions=[(163, 25), (287, 25), (417, 25)],
                                     common_edges=[{'pos': (30, 30), 'dst': options_page}])

    fight_prepare_page = construct_node(timer, 'fight_prepare_page', map_page)
    backyard_page = construct_node(timer, 'backyard_page', main_page)
    bath_page = construct_node(timer, 'bath_page', backyard_page)
    choose_repair_page = construct_node(timer, 'choose_repair_page', bath_page)
    canteen_page = construct_node(timer, 'canteen_page', backyard_page)
    mission_page = construct_node(timer, 'mission_page', main_page)
    support_set_page = construct_node(timer, 'support_set_page', main_page)
    friend_page = construct_node(timer, 'friend_page', options_page)

    add_edge(timer, main_page, map_page, construct_clicks_method(timer, [(900, 480, 1, 0)]), expedition_page)
    add_edge(timer, main_page, mission_page, construct_clicks_method(timer, [(656, 480, 1, 0)]))
    add_edge(timer, main_page, backyard_page, construct_clicks_method(timer, [(45, 80, 1, 0)]))
    add_edge(timer, main_page, support_set_page, construct_clicks_method(timer, [(50, 135, 1, 1), (200, 300, 1, 1)]))
    add_edge(timer, main_page, options_page, construct_clicks_method(timer, [(42, 484, 1, 0)]))

    add_edge(timer, map_page, fight_prepare_page, construct_clicks_method(timer, [(600, 300, 1, 0)]))

    add_edge(timer, fight_prepare_page, map_page, construct_clicks_method(timer, [(30, 30, 1, 0)]))
    add_edge(timer, fight_prepare_page, bath_page, construct_clicks_method(timer, [(840, 20, 1, 0)]))

    add_edge(timer, options_page, build_page, construct_clicks_method(
        timer, [(150, 200, 1, 1.25), (360, 200, 1, 0)]), develop_page)
    add_edge(timer, options_page, remake_page, construct_clicks_method(timer, [(150, 270, 1, 1.25), (360, 270, 1, 0)]))
    add_edge(timer, options_page, friend_page, construct_clicks_method(timer, [(150, 410, 1, 0)]))
    add_edge(timer, options_page, main_page, construct_clicks_method(timer, [(36, 500, 1, 0)]))

    add_edge(timer, backyard_page, canteen_page, construct_clicks_method(timer, [(700, 400, 1, 0)]))
    add_edge(timer, backyard_page, bath_page, construct_clicks_method(timer, [(300, 200, 1, 0)]))
    add_edge(timer, backyard_page, main_page, construct_clicks_method(timer, [(50, 30, 1, 0)]))

    add_edge(timer, bath_page, main_page, construct_clicks_method(timer, [(120, 30, 1, 0)]))
    add_edge(timer, bath_page, choose_repair_page, construct_clicks_method(timer, [(900, 30, 1, 0)]))

    add_edge(timer, choose_repair_page, bath_page, construct_clicks_method(timer, [(916, 45, 1, 0)]))

    add_edge(timer, canteen_page, main_page, construct_clicks_method(timer, [(120, 30, 1, 0)]))
    add_edge(timer, canteen_page, backyard_page, construct_clicks_method(timer, [(50, 30, 1, 0)]))

    add_edge(timer, mission_page, main_page, construct_clicks_method(timer, [(30, 30, 1, 0)]))

    add_edge(timer, support_set_page, main_page, construct_clicks_method(timer, [(30, 30, 1, .5), (50, 30, 1, .5)]))

    add_edge(timer, friend_page, options_page, construct_clicks_method(timer, [(30, 30, 1, 0)]))

    ui_tree.dfs(main_page)

    timer.ui = ui_tree
