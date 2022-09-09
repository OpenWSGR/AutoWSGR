"""获取 UI 树
"""


page_count = 0
ui_tree = None
function_tree = None


class SwitchMethod():
    def __init__(self, fun_list):
        self.operates = fun_list

    def operate(self):
        res = []
        for operation in self.operates:
            res.append(operation)
        return res

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
        return choice(edges) if len(edges) != 0 else None

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

    def __init__(self, operate_fun: SwitchMethod, u: Node, v: Node, other_dst=None, extra_op: SwitchMethod = None):
        self.operate_fun = operate_fun
        self.u = u
        self.v = v
        self.other_dst = other_dst
        self.extra_op = extra_op

    def operate(self):
        return self.operate_fun.operate()
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

        while (start != lca):
            path1.append(start)
            start = start.father
        while (end != lca):
            path2.append(end)
            end = end.father
        path2.reverse()
        path = path1 + [lca] + path2
        result, i = [], 0
        while (i < len(path)):
            node = path[i]
            result.append(node)
            if (node.find_edge(path[-1]) != None):
                return result + [path[-1]]
            for j in range(i + 2, len(path)):
                dst = path[j]
                if (node.find_edge(dst) != None):
                    i = j - 1
            i += 1
        return result

    def lca(self, u: Node, v: Node) -> Node:
        if (v.depth > u.depth):
            return self.lca(v, u)
        if (u == v):
            return v
        if (u.depth == v.depth):
            return self.lca(u.father, v.father)
        return self.lca(u.father, v)

    def dfs(self, u: Node):
        for edge in u.edges:
            son = edge.v
            if (son == u.father or son.father != u):
                continue

            son.depth = u.depth + 1
            self.dfs(son)

    

    def get_node_by_name(self, name):
        return self.nodes.get(name)

    def print(self):

        for node in self.nodes.values():
            node.print()

    def page_exist(self, page):
        return page in self.nodes.values()



def list_walk_path(start: Node, end: Node):
    global ui_tree
    path = ui_tree.find_path(start, end)
    for node in path:
        print(node, end="->")


def construct_node(name: str, father):
    global page_count, ui_tree
    page_count += 1
    node = Node(name, page_count)
    node.set_father(father)
    ui_tree.add_node(node)
    return node


def construct_clicks_method(click_position_args):
    operations = [["click", operation] for operation in click_position_args]

    return SwitchMethod(operations)


def add_edge(u: Node, v: Node, method: SwitchMethod, other_dst=None):
    edge = Edge(method, u, v, other_dst=other_dst)
    u.add_edge(edge)


def construct_intergrative_pages(father, click_positions=[], names=[], common_edges=[]):
    assert len(click_positions) == len(names)
    first_node = construct_node(names[0], father)
    nodes = [first_node]
    for name in names[1:]:
        nodes.append(construct_node(name, first_node))
    for i, node in enumerate(nodes):
        for j, click_position in enumerate(click_positions):
            if i == j:
                continue
            add_edge(node, nodes[j], construct_clicks_method([click_position]))

        for edge in common_edges:
            dst = edge.get('dst')
            x, y = edge.get('pos')
            add_edge(node, dst, construct_clicks_method([(x, y)]))
    return nodes


def load_game_ui():
    global ui_tree, function_tree
    ui_tree = UI()

    main_page = construct_node('main_page', None)
    map_page, exercise_page, expedition_page, battle_page, decisive_battle_entrance = \
        construct_intergrative_pages(main_page, names=['map_page', 'exercise_page', 'expedition_page', 'battle_page', 'decisive_battle_entrance'],
                                     click_positions=[(163, 25), (287, 25), (417, 25), (544, 25), (661, 25)],
                                     common_edges=[{'pos': (30, 30), 'dst': main_page}])

    options_page = construct_node('options_page', main_page)
    build_page, destroy_page, develop_page, discard_page = \
        construct_intergrative_pages(options_page, names=['build_page', 'destroy_page', 'develop_page', 'discard_page', ],
                                     click_positions=[(163, 25), (287, 25), (417, 25), (544, 25)],
                                     common_edges=[{'pos': (30, 30), 'dst': options_page}])
    intensify_page, remake_page, skill_page = \
        construct_intergrative_pages(options_page, names=['intensify_page', 'remake_page', 'skill_page', ],
                                     click_positions=[(163, 25), (287, 25), (417, 25)],
                                     common_edges=[{'pos': (30, 30), 'dst': options_page}])

    fight_prepare_page = construct_node('fight_prepare_page', map_page)
    backyard_page = construct_node('backyard_page', main_page)
    bath_page = construct_node('bath_page', backyard_page)
    choose_repair_page = construct_node('choose_repair_page', bath_page)
    canteen_page = construct_node('canteen_page', backyard_page)
    mission_page = construct_node('mission_page', main_page)
    support_set_page = construct_node('support_set_page', main_page)
    friend_page = construct_node('friend_page', options_page)

    add_edge(main_page, map_page, construct_clicks_method([(900, 480, 1, 0)]), expedition_page)
    add_edge(main_page, mission_page, construct_clicks_method([(656, 480, 1, 0)]))
    add_edge(main_page, backyard_page, construct_clicks_method([(45, 80, 1, 0)]))
    add_edge(main_page, support_set_page, construct_clicks_method([(50, 135, 1, 1), (200, 300, 1, 1)]))
    add_edge(main_page, options_page, construct_clicks_method([(42, 484, 1, 0)]))

    add_edge(map_page, fight_prepare_page, construct_clicks_method([(600, 300, 1, 0)]))

    add_edge(fight_prepare_page, map_page, construct_clicks_method([(30, 30, 1, 0)]))
    add_edge(fight_prepare_page, bath_page, construct_clicks_method([(840, 20, 1, 0)]))

    add_edge(options_page, build_page, construct_clicks_method(
        [(150, 200, 1, 1.25), (360, 200, 1, 0)]), develop_page)
    add_edge(options_page, remake_page, construct_clicks_method([(150, 270, 1, 1.25), (360, 270, 1, 0)]))
    add_edge(options_page, friend_page, construct_clicks_method([(150, 410, 1, 0)]))
    add_edge(options_page, main_page, construct_clicks_method([(36, 500, 1, 0)]))

    add_edge(backyard_page, canteen_page, construct_clicks_method([(700, 400, 1, 0)]))
    add_edge(backyard_page, bath_page, construct_clicks_method([(300, 200, 1, 0)]))
    add_edge(backyard_page, main_page, construct_clicks_method([(50, 30, 1, 0)]))

    add_edge(bath_page, main_page, construct_clicks_method([(120, 30, 1, 0)]))
    add_edge(bath_page, choose_repair_page, construct_clicks_method([(900, 30, 1, 0)]))

    add_edge(choose_repair_page, bath_page, construct_clicks_method([(916, 45, 1, 0)]))

    add_edge(canteen_page, main_page, construct_clicks_method([(120, 30, 1, 0)]))
    add_edge(canteen_page, backyard_page, construct_clicks_method([(50, 30, 1, 0)]))

    add_edge(mission_page, main_page, construct_clicks_method([(30, 30, 1, 0)]))

    add_edge(support_set_page, main_page, construct_clicks_method([(30, 30, 1, .5), (50, 30, 1, .5)]))

    add_edge(friend_page, options_page, construct_clicks_method([(30, 30, 1, 0)]))

    ui_tree.dfs(main_page)

    return ui_tree
