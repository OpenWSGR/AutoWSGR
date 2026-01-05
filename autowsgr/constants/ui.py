"""UI 树模块

本模块实现了游戏 UI 界面的树形结构，用于管理页面间的导航和切换。
"""

from __future__ import annotations

from random import choice
from typing import TYPE_CHECKING, Dict, Tuple, Union

if TYPE_CHECKING:
    from collections.abc import Sequence

# 类型别名
ClickPosition = Union[Tuple[int, int], Tuple[int, int, int, float]]
EdgeConfig = Dict[str, Union[Tuple[int, int], 'Node']]


class SwitchMethod:
    """页面切换操作方法"""

    def __init__(self, fun_list: list) -> None:
        self.operates = fun_list

    def operate(self) -> list:
        return list(self.operates)

    def print(self) -> None:
        for operation in self.operates:
            print(operation, end=' ')


class Node:
    """UI 树节点

    保存 UI 树的节点信息，包括节点名称、父子关系和连接边。
    """

    def __init__(self, name: str, node_id: int) -> None:
        self.id: int = node_id
        self.name: str = name
        self.father_edge: Edge | None = None
        self.father: Node | None = None
        self.depth: int = 0
        self.edges: list[Edge] = []

    def set_father(self, father: Node | None) -> None:
        self.father = father
        self.father_edge = self.find_edge(father) if father else None

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def find_edges(self, target: Node | None) -> list[Edge]:
        return [edge for edge in self.edges if edge.v is target]

    def find_edge(self, target: Node | None) -> Edge | None:
        edges = self.find_edges(target)
        return choice(edges) if edges else None

    def print(self) -> None:
        print('节点名:', self.name, '节点编号:', self.id)
        print('父节点:', self.father)
        print('节点连边:')
        for edge in self.edges:
            edge.print()

    def __str__(self) -> str:
        return self.name


class Edge:
    """UI 图的边

    保存 UI 图中两个节点之间的连接关系和切换操作。
    """

    def __init__(
        self,
        operate_fun: SwitchMethod,
        u: Node,
        v: Node,
        other_dst: Node | None = None,
        extra_op: SwitchMethod | None = None,
    ) -> None:
        self.operate_fun = operate_fun
        self.u = u
        self.v = v
        self.other_dst = other_dst
        self.extra_op = extra_op

    def operate(self) -> list:
        return self.operate_fun.operate()

    def print(self) -> None:
        print('起点:', self.u.name, '终点:', self.v.name)


class UI:
    """UI 树（拓扑学概念）

    管理游戏界面的树形结构，提供页面导航和路径查找功能。
    """

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.page_count: int = 0
        self.is_normal_fight_prepare: bool = False
        self._build_ui_tree()

    # ==================== 公共接口 ====================

    def get_node_by_name(self, name: str) -> Node | None:
        return self.nodes.get(name)

    def page_exist(self, page: Node) -> bool:
        return page in self.nodes.values()

    def find_path(self, start: Node, end: Node) -> list[Node]:
        """查找从起点到终点的最短路径"""
        lca = self._find_lca(start, end)
        path_to_lca = self._collect_path_to_ancestor(start, lca)
        path_from_lca = self._collect_path_to_ancestor(end, lca)
        path_from_lca.reverse()

        full_path: list[Node] = [*path_to_lca, lca, *path_from_lca]
        return self._optimize_path(full_path)

    def print(self) -> None:
        for node in self.nodes.values():
            node.print()

    # ==================== 路径查找辅助方法 ====================

    def _collect_path_to_ancestor(self, node: Node, ancestor: Node) -> list[Node]:
        """收集从节点到祖先节点的路径（不包含祖先）"""
        path = []
        while node != ancestor:
            path.append(node)
            assert node.father is not None
            node = node.father
        return path

    def _optimize_path(self, path: list[Node]) -> list[Node]:
        """优化路径，利用直接边跳过中间节点"""
        result: list[Node] = []
        i = 0
        while i < len(path):
            node = path[i]
            result.append(node)
            # 检查是否可以直接到达终点
            if node.find_edge(path[-1]) is not None:
                return [*result, path[-1]]
            # 检查是否可以跳过中间节点
            for j in range(i + 2, len(path)):
                if node.find_edge(path[j]) is not None:
                    i = j - 1
                    break
            i += 1
        return result

    def _find_lca(self, u: Node, v: Node) -> Node:
        """查找两个节点的最近公共祖先（LCA）"""
        # 确保 u 的深度不小于 v
        if v.depth > u.depth:
            u, v = v, u
        # 将 u 提升到与 v 相同深度
        while u.depth > v.depth:
            assert u.father is not None
            u = u.father
        # 同时向上查找
        while u != v:
            assert u.father is not None and v.father is not None
            u, v = u.father, v.father
        return u

    # ==================== 树构建方法 ====================

    def _build_ui_tree(self) -> None:
        """构建完整的 UI 树"""
        main_page = self._create_main_page_subtree()
        self._calculate_node_depths(main_page)

    def _create_main_page_subtree(self) -> Node:
        """创建以主页面为根的子树"""
        main_page = self._construct_node('main_page', None)

        # 构建各个子模块
        map_page, expedition_page = self._create_navigation_pages(main_page)
        options_page, build_page, develop_page, remake_page, friend_page = (
            self._create_options_pages(main_page)
        )
        backyard_page, bath_page, canteen_page, choose_repair_page = (
            self._create_backyard_pages(main_page)
        )
        fight_prepare_page = self._construct_node('fight_prepare_page', map_page)
        mission_page = self._construct_node('mission_page', main_page)
        support_set_page = self._construct_node('support_set_page', main_page)

        # 添加页面间的边
        self._add_main_page_edges(
            main_page, map_page, expedition_page, mission_page,
            backyard_page, support_set_page, options_page,
        )
        self._add_map_page_edges(map_page, fight_prepare_page, bath_page)
        self._add_options_page_edges(
            options_page, main_page, build_page, develop_page, remake_page, friend_page,
        )
        self._add_backyard_page_edges(
            backyard_page, main_page, bath_page, canteen_page, choose_repair_page,
        )
        self._add_other_page_edges(mission_page, support_set_page, friend_page, main_page, options_page)

        return main_page

    def _create_navigation_pages(self, main_page: Node) -> tuple[Node, Node]:
        """创建导航栏页面（出征、演习、远征等）"""
        pages = self._construct_integrative_pages(
            main_page,
            names=['map_page', 'exercise_page', 'expedition_page', 'battle_page', 'decisive_battle_entrance'],
            click_positions=[(163, 25), (287, 25), (417, 25), (544, 25), (661, 25)],
            common_edges=[{'pos': (30, 30), 'dst': main_page}],
        )
        map_page, _exercise_page, expedition_page, _battle_page, _decisive_battle_entrance = pages
        return map_page, expedition_page

    def _create_options_pages(self, main_page: Node) -> tuple[Node, Node, Node, Node, Node]:
        """创建选项相关页面（建造、开发等）"""
        options_page = self._construct_node('options_page', main_page)

        # 建造/解体/开发/废弃页面组
        build_pages = self._construct_integrative_pages(
            options_page,
            names=['build_page', 'destroy_page', 'develop_page', 'discard_page'],
            click_positions=[(163, 25), (287, 25), (417, 25), (544, 25)],
            common_edges=[{'pos': (30, 30), 'dst': options_page}],
        )
        build_page, _destroy_page, develop_page, _discard_page = build_pages

        # 强化/改造/技能页面组
        enhance_pages = self._construct_integrative_pages(
            options_page,
            names=['intensify_page', 'remake_page', 'skill_page'],
            click_positions=[(163, 25), (287, 25), (417, 25)],
            common_edges=[{'pos': (30, 30), 'dst': options_page}],
        )
        _intensify_page, remake_page, _skill_page = enhance_pages

        friend_page = self._construct_node('friend_page', options_page)

        return options_page, build_page, develop_page, remake_page, friend_page

    def _create_backyard_pages(self, main_page: Node) -> tuple[Node, Node, Node, Node]:
        """创建后院相关页面（澡堂、食堂等）"""
        backyard_page = self._construct_node('backyard_page', main_page)
        bath_page = self._construct_node('bath_page', backyard_page)
        canteen_page = self._construct_node('canteen_page', backyard_page)
        choose_repair_page = self._construct_node('choose_repair_page', bath_page)
        return backyard_page, bath_page, canteen_page, choose_repair_page

    # ==================== 边添加方法 ====================

    def _add_main_page_edges(
        self,
        main_page: Node,
        map_page: Node,
        expedition_page: Node,
        mission_page: Node,
        backyard_page: Node,
        support_set_page: Node,
        options_page: Node,
    ) -> None:
        """添加主页面的出边"""
        edges_config = [
            (map_page, [(900, 480, 1, 0)], expedition_page),
            (mission_page, [(656, 480, 1, 0)], None),
            (backyard_page, [(45, 80, 1, 0)], None),
            (support_set_page, [(50, 135, 1, 1), (200, 300, 1, 1)], None),
            (options_page, [(42, 484, 1, 0)], None),
        ]
        for target, clicks, other_dst in edges_config:
            self._add_edge(main_page, target, self._construct_clicks_method(clicks), other_dst)

    def _add_map_page_edges(
        self,
        map_page: Node,
        fight_prepare_page: Node,
        bath_page: Node,
    ) -> None:
        """添加地图页面相关的边"""
        self._add_edge(map_page, fight_prepare_page, self._construct_clicks_method([(600, 300, 1, 0)]))
        self._add_edge(fight_prepare_page, map_page, self._construct_clicks_method([(33, 30, 1, 0)]))
        self._add_edge(fight_prepare_page, bath_page, self._construct_clicks_method([(840, 20, 1, 0)]))

    def _add_options_page_edges(
        self,
        options_page: Node,
        main_page: Node,
        build_page: Node,
        develop_page: Node,
        remake_page: Node,
        friend_page: Node,
    ) -> None:
        """添加选项页面的边"""
        self._add_edge(
            options_page, build_page,
            self._construct_clicks_method([(150, 200, 1, 1.25), (360, 200, 1, 0)]),
            develop_page,
        )
        self._add_edge(
            options_page, remake_page,
            self._construct_clicks_method([(150, 270, 1, 1.25), (360, 270, 1, 0)]),
        )
        self._add_edge(options_page, friend_page, self._construct_clicks_method([(150, 410, 1, 0)]))
        self._add_edge(options_page, main_page, self._construct_clicks_method([(36, 500, 1, 0)]))

    def _add_backyard_page_edges(
        self,
        backyard_page: Node,
        main_page: Node,
        bath_page: Node,
        canteen_page: Node,
        choose_repair_page: Node,
    ) -> None:
        """添加后院相关页面的边"""
        # 后院页面的边
        self._add_edge(backyard_page, canteen_page, self._construct_clicks_method([(700, 400, 1, 0)]))
        self._add_edge(backyard_page, bath_page, self._construct_clicks_method([(300, 200, 1, 0)]))
        self._add_edge(backyard_page, main_page, self._construct_clicks_method([(50, 30, 1, 0)]))
        # 澡堂页面的边
        self._add_edge(bath_page, main_page, self._construct_clicks_method([(120, 30, 1, 0)]))
        self._add_edge(bath_page, choose_repair_page, self._construct_clicks_method([(900, 30, 1, 0)]))
        # 选择修理页面的边
        self._add_edge(choose_repair_page, bath_page, self._construct_clicks_method([(916, 45, 1, 0)]))
        # 食堂页面的边
        self._add_edge(canteen_page, main_page, self._construct_clicks_method([(120, 30, 1, 0)]))
        self._add_edge(canteen_page, backyard_page, self._construct_clicks_method([(50, 30, 1, 0)]))

    def _add_other_page_edges(
        self,
        mission_page: Node,
        support_set_page: Node,
        friend_page: Node,
        main_page: Node,
        options_page: Node,
    ) -> None:
        """添加其他页面的边"""
        self._add_edge(mission_page, main_page, self._construct_clicks_method([(30, 30, 1, 0)]))
        self._add_edge(
            support_set_page, main_page,
            self._construct_clicks_method([(30, 30, 1, 0.5), (50, 30, 1, 0.5)]),
        )
        self._add_edge(friend_page, options_page, self._construct_clicks_method([(30, 30, 1, 0)]))

    def _calculate_node_depths(self, root: Node) -> None:
        """计算所有节点的深度（DFS）"""
        for edge in root.edges:
            child = edge.v
            if child == root.father or child.father != root:
                continue
            child.depth = root.depth + 1
            self._calculate_node_depths(child)

    # ==================== 节点和边的基础构建方法 ====================

    def _add_node(self, node: Node) -> None:
        self.nodes[node.name] = node

    def _dfs(self, u: Node) -> None:
        """保留的 DFS 方法，用于兼容性"""
        self._calculate_node_depths(u)

    def _list_walk_path(self, start: Node, end: Node) -> None:
        """打印从起点到终点的路径"""
        path = self.find_path(start, end)
        for node in path:
            print(node, end='->')

    def _construct_node(self, name: str, father: Node | None) -> Node:
        """创建并注册新节点"""
        self.page_count += 1
        node = Node(name, self.page_count)
        node.set_father(father)
        self._add_node(node)
        return node

    def _construct_clicks_method(
        self,
        click_position_args: Sequence[ClickPosition],
    ) -> SwitchMethod:
        """构建点击操作方法"""
        operations = [['click', pos] for pos in click_position_args]
        return SwitchMethod(operations)

    def _add_edge(
        self,
        u: Node,
        v: Node,
        method: SwitchMethod,
        other_dst: Node | None = None,
    ) -> None:
        """添加有向边"""
        edge = Edge(method, u, v, other_dst=other_dst)
        u.add_edge(edge)

    def _construct_integrative_pages(
        self,
        father: Node,
        click_positions: list[ClickPosition] | None = None,
        names: list[str] | None = None,
        common_edges: list[EdgeConfig] | None = None,
    ) -> list[Node]:
        """构建一组互相连通的页面

        这些页面通常是顶部标签栏页面，可以互相切换。
        """
        click_positions = click_positions or []
        names = names or []
        common_edges = common_edges or []

        assert len(click_positions) == len(names), '点击位置数量必须与页面名称数量一致'

        # 创建节点：第一个节点以 father 为父节点，其余节点以第一个节点为父节点
        first_node = self._construct_node(names[0], father)
        nodes = [first_node] + [
            self._construct_node(name, first_node) for name in names[1:]
        ]

        # 添加页面间的互相切换边
        for i, src_node in enumerate(nodes):
            for j, click_pos in enumerate(click_positions):
                if i != j:
                    self._add_edge(
                        src_node, nodes[j],
                        self._construct_clicks_method([click_pos]),
                    )
            # 添加公共边（如返回按钮）
            for edge_config in common_edges:
                dst = edge_config.get('dst')
                pos = edge_config.get('pos')
                if dst and pos:
                    x, y = pos
                    self._add_edge(src_node, dst, self._construct_clicks_method([(x, y)]))

        return nodes


WSGR_UI = UI()
