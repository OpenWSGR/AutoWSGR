"""获取 UI 树
"""


class SwitchMethod():
    def __init__(self, fun_list):
        self.operates = fun_list

    def operate(self):
        res = list(self.operates)
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

    def print(self,):
        print("起点:", self.u.name, "终点:", self.v.name)


class UI():
    """UI树(拓扑学概念)
    """

    def __init__(self):
        self.nodes = {}
        self.page_count = 0

        self._build_ui_tree()

    def get_node_by_name(self, name):
        return self.nodes.get(name)

    def page_exist(self, page):
        return page in self.nodes.values()

    def find_path(self, start: Node, end: Node):

        lca = self._lca(start, end)
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

    def print(self):
        for node in self.nodes.values():
            node.print()

    def _build_ui_tree(self):

        main_page = self._construct_node('main_page', None)
        map_page, exercise_page, expedition_page, battle_page, decisive_battle_entrance = \
            self._construct_integrative_pages(main_page, names=['map_page', 'exercise_page', 'expedition_page', 'battle_page', 'decisive_battle_entrance'],
                                               click_positions=[(163, 25), (287, 25), (417, 25), (544, 25), (661, 25)],
                                               common_edges=[{'pos': (30, 30), 'dst': main_page}])

        options_page = self._construct_node('options_page', main_page)
        build_page, destroy_page, develop_page, discard_page = \
            self._construct_integrative_pages(options_page, names=['build_page', 'destroy_page', 'develop_page', 'discard_page', ],
                                               click_positions=[(163, 25), (287, 25), (417, 25), (544, 25)],
                                               common_edges=[{'pos': (30, 30), 'dst': options_page}])
        intensify_page, remake_page, skill_page = \
            self._construct_integrative_pages(options_page, names=['intensify_page', 'remake_page', 'skill_page', ],
                                               click_positions=[(163, 25), (287, 25), (417, 25)],
                                               common_edges=[{'pos': (30, 30), 'dst': options_page}])

        fight_prepare_page = self._construct_node('fight_prepare_page', map_page)
        backyard_page = self._construct_node('backyard_page', main_page)
        bath_page = self._construct_node('bath_page', backyard_page)
        choose_repair_page = self._construct_node('choose_repair_page', bath_page)
        canteen_page = self._construct_node('canteen_page', backyard_page)
        mission_page = self._construct_node('mission_page', main_page)
        support_set_page = self._construct_node('support_set_page', main_page)
        friend_page = self._construct_node('friend_page', options_page)

        self._add_edge(main_page, map_page, self._construct_clicks_method([(900, 480, 1, 0)]), expedition_page)
        self._add_edge(main_page, mission_page, self._construct_clicks_method([(656, 480, 1, 0)]))
        self._add_edge(main_page, backyard_page, self._construct_clicks_method([(45, 80, 1, 0)]))
        self._add_edge(main_page, support_set_page, self._construct_clicks_method([(50, 135, 1, 1), (200, 300, 1, 1)]))
        self._add_edge(main_page, options_page, self._construct_clicks_method([(42, 484, 1, 0)]))

        self._add_edge(map_page, fight_prepare_page, self._construct_clicks_method([(600, 300, 1, 0)]))

        self._add_edge(fight_prepare_page, map_page, self._construct_clicks_method([(30, 30, 1, 0)]))
        self._add_edge(fight_prepare_page, bath_page, self._construct_clicks_method([(840, 20, 1, 0)]))

        self._add_edge(options_page, build_page, self._construct_clicks_method(
            [(150, 200, 1, 1.25), (360, 200, 1, 0)]), develop_page)
        self._add_edge(options_page, remake_page, self._construct_clicks_method([(150, 270, 1, 1.25), (360, 270, 1, 0)]))
        self._add_edge(options_page, friend_page, self._construct_clicks_method([(150, 410, 1, 0)]))
        self._add_edge(options_page, main_page, self._construct_clicks_method([(36, 500, 1, 0)]))

        self._add_edge(backyard_page, canteen_page, self._construct_clicks_method([(700, 400, 1, 0)]))
        self._add_edge(backyard_page, bath_page, self._construct_clicks_method([(300, 200, 1, 0)]))
        self._add_edge(backyard_page, main_page, self._construct_clicks_method([(50, 30, 1, 0)]))

        self._add_edge(bath_page, main_page, self._construct_clicks_method([(120, 30, 1, 0)]))
        self._add_edge(bath_page, choose_repair_page, self._construct_clicks_method([(900, 30, 1, 0)]))

        self._add_edge(choose_repair_page, bath_page, self._construct_clicks_method([(916, 45, 1, 0)]))

        self._add_edge(canteen_page, main_page, self._construct_clicks_method([(120, 30, 1, 0)]))
        self._add_edge(canteen_page, backyard_page, self._construct_clicks_method([(50, 30, 1, 0)]))

        self._add_edge(mission_page, main_page, self._construct_clicks_method([(30, 30, 1, 0)]))

        self._add_edge(support_set_page, main_page, self._construct_clicks_method([(30, 30, 1, .5), (50, 30, 1, .5)]))

        self._add_edge(friend_page, options_page, self._construct_clicks_method([(30, 30, 1, 0)]))

        self._dfs(main_page)

    def _add_node(self, node: Node):
        self.nodes[node.name] = node

    def _lca(self, u: Node, v: Node) -> Node:
        if (v.depth > u.depth):
            return self._lca(v, u)
        if (u == v):
            return v
        if (u.depth == v.depth):
            return self._lca(u.father, v.father)
        return self._lca(u.father, v)

    def _dfs(self, u: Node):
        for edge in u.edges:
            son = edge.v
            if (son == u.father or son.father != u):
                continue

            son.depth = u.depth + 1
            self._dfs(son)

    def _list_walk_path(self, start: Node, end: Node):
        path = self.find_path(start, end)
        for node in path:
            print(node, end="->")

    def _construct_node(self, name: str, father):
        self.page_count += 1
        node = Node(name, self.page_count)
        node.set_father(father)
        self._add_node(node)
        return node

    def _construct_clicks_method(self, click_position_args):
        operations = [["click", operation] for operation in click_position_args]

        return SwitchMethod(operations)

    def _add_edge(self, u: Node, v: Node, method: SwitchMethod, other_dst=None):
        edge = Edge(method, u, v, other_dst=other_dst)
        u.add_edge(edge)

    def _construct_integrative_pages(self, father, click_positions=[], names=[], common_edges=[]):
        assert len(click_positions) == len(names)
        first_node = self._construct_node(names[0], father)
        nodes = [first_node]
        for name in names[1:]:
            nodes.append(self._construct_node(name, first_node))
        for i, node in enumerate(nodes):
            for j, click_position in enumerate(click_positions):
                if i == j:
                    continue
                self._add_edge(node, nodes[j], self._construct_clicks_method([click_position]))

            for edge in common_edges:
                dst = edge.get('dst')
                x, y = edge.get('pos')
                self._add_edge(node, dst, self._construct_clicks_method([(x, y)]))
        return nodes


WSGR_UI = UI()
