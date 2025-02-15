import os
from collections.abc import Iterable

import cv2

from autowsgr.constants.data_roots import OCR_ROOT
from autowsgr.constants.image_templates import IMG
from autowsgr.constants.positions import FLEET_POSITION
from autowsgr.game.game_operation import move_team
from autowsgr.timer import Timer
from autowsgr.utils.api_image import absolute_to_relative, crop_rectangle_relative
from autowsgr.utils.io import yaml_to_dict
from autowsgr.utils.operator import unorder_equal


POS = yaml_to_dict(os.path.join(OCR_ROOT, 'relative_location.yaml'))


def count_ship(fleet):
    return sum(have_ship(fleet[i]) for i in range(1, min(len(fleet), 7)))


def have_ship(ship):
    return ship is not None and ship != ''


class Fleet:
    levels: list[int | None]

    def __init__(self, timer: Timer, fleet_id=None) -> None:
        self.timer = timer
        self.fleet_id = fleet_id
        self.flag_ship = None
        self.ships = [None] * 7

    def exist(self, name):
        return name in self.ships

    def empty(self):
        return self.count() == 0

    def count(self):
        return 0 if self.ships is None else count_ship(self.ships)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Iterable | Fleet):
            raise TypeError
        ships = other
        if isinstance(other, Fleet):
            if other.fleet_id != self.fleet_id:
                return False
            ships = other.ships

        for i in range(1, 7):
            if have_ship(ships[i]) != have_ship(self.ships[i]) or (
                have_ship(ships[i]) and ships[i] != self.ships[i]
            ):
                return False
        return True

    def detect(self, check_level=False, reg=False):
        """在对应的战斗准备页面检查舰船"""
        assert self.timer.wait_image(IMG.identify_images['fight_prepare_page'])

        if self.fleet_id is not None:
            move_team(self.timer, self.fleet_id)

        ships = self.timer.recognize(
            self.timer.get_screen()[433:459],
            candidates=self.timer.ship_names,
            multiple=True,
        )
        self.ships = [None] * 7

        for rk, ship in enumerate(ships):
            if reg and not self.timer.port.have_ship():
                self.timer.port.register_ship(ship[1])
            self.ships[rk + 1] = ship[1]
        self.timer.logger.info(f'舰船识别结果为: {self.ships}')

        try:
            self.check_level()
        except IndexError as e:
            self.timer.logger.info('检查等级失败')
            if check_level:
                raise e

    def check_level(self):
        LEFT_TOPS = [
            (0.069, 0.566),
            (0.186, 0.566),
            (0.303, 0.566),
            (0.420, 0.566),
            (0.537, 0.566),
            (0.654, 0.566),
        ]
        SIZE = (0.023, 0.024)
        screen = self.timer.get_screen()
        self.levels = [None] * 7
        for i in range(1, count_ship(self.ships) + 1):
            img = crop_rectangle_relative(
                screen,
                LEFT_TOPS[i - 1][0],
                LEFT_TOPS[i - 1][1],
                SIZE[0],
                SIZE[1],
            )
            img = cv2.resize(img, (img.shape[1] * 4, img.shape[0] * 4))
            # cv_show_image(img)
            recognize_result = self.timer.ocr_backend.recognize_number(img, min_size=3)
            assert recognize_result is not None
            self.levels[i] = int(recognize_result[1])
            # print(levels)
        self.timer.logger.info(f'等级识别结果: {self.levels}')

    def _change_ship(self, position, ship_name, search_method='word'):
        self.ships[position] = ship_name
        self.timer.click(*FLEET_POSITION[position], delay=0)
        res = self.timer.wait_images(
            IMG.choose_ship_image[1:3] + [IMG.choose_ship_image[4]],
            after_get_delay=0.4,
            gap=0,
            timeout=16,
        )
        if res is None:
            raise TimeoutError('选择舰船时点击超时')
        if ship_name is None:
            self.timer.click(83, 167, delay=0)
        else:
            if res == 1:
                self.timer.relative_click(0.875, 0.246)
            if search_method == 'word':
                self.timer.relative_click(0.729, 0.056, delay=0)
                self.timer.wait_image(
                    IMG.choose_ship_image[3],
                    gap=0,
                    after_get_delay=0.1,
                )
                self.timer.text(ship_name)
                self.timer.click(1219 * 0.75, 667 * 0.75, delay=1)

            ships = self.timer.recognize_ship(
                self.timer.get_screen()[:, :1048],
                self.timer.ship_names,
            )
            self.timer.logger.info(f'更改编队可用舰船：{[item[1] for item in ships]}')
            for ship in ships:
                if ship[1] == ship_name:
                    rel_center = absolute_to_relative(ship[0], (1280, 720))
                    self.timer.relative_click(*rel_center)
                    break

        self.timer.wait_pages('fight_prepare_page', gap=0)

    def _set_ships(self, ships, search_method='word'):
        """
        将当前舰队设置为指定的舰船，ships是要设置的舰队，self.ships是当前舰队
        Args:
            ships (list(str)): 要设置的舰船 [0号位留空, 1号位, 2号位, ...]
            search_method (str): "word" or "image"

        """
        ok = [None] + [False] * 6
        if self.ships is None:
            self.detect()
        for i in range(1, 7):
            ship = self.ships[i]
            if not have_ship(ship):
                continue
            if ship in ships:
                ok[i] = True
        for ship in ships:
            if ship in self.ships or not have_ship(ship):
                continue
            position = ok.index(False)
            self.timer.logger.debug(f'更改{position}号位舰船为 {ship}')
            self._change_ship(position, ship, search_method=search_method)
            ok[position] = True

        # 删除多余舰船，如果在设置中某个位置为更改舰船，而且self.ships中有舰船，则去除舰船后删除
        for i in range(1, 7):
            if not ok[7 - i] and self.ships[7 - i] is not None:
                self._change_ship(7 - i, None)
                self.ships[7 - i :] = self.ships[8 - i :]
                self.ships.append(None)

    def reorder(self, ships):
        assert unorder_equal(ships, self.ships, skip=[None, ''])
        for i in range(1, 7):
            ship = ships[i]
            if not have_ship(ship):
                return
            if self.ships[i] != ship:
                self.circular_move(self.ships.index(ship), i)

    def circular_move(self, p1, p2):
        if p1 > p2:
            self.ships = (
                self.ships[:p2] + self.ships[p1 : p1 + 1] + self.ships[p2:p1] + self.ships[p1 + 1 :]
            )
        else:
            self.ships = (
                self.ships[:p1]
                + self.ships[p1 + 1 : p2 + 1]
                + self.ships[p1 : p1 + 1]
                + self.ships[p2 + 1 :]
            )
        assert len(self.ships) == 7
        p1 = FLEET_POSITION[p1]
        p2 = FLEET_POSITION[p2]
        self.timer.swipe(*p1, *p2)

    def legal(self, ships):
        ok = False
        # 如果舰队长度小于等于7，加上7个None
        while len(ships) < 7:
            ships.append('')
        for i in range(1, 7):
            if ships[i] is None:
                ok = True
            if ok and ships[i] is not None:
                return False
        return True

    def set_ship(self, ships, flag_ship=None, order=False, search_method='word'):
        """设置指定位置的舰队, 1-index
        Args:
            ships (list(str)): 代表舰船 [0号位留空, 1号位, 2号位, ...]
            flag_ship: 如果不为 None, 则代表旗舰名称
            order (bool): 是否按照 ships 给定的顺序 (优先级高于旗舰指定)
            search_method: 检索方式 "word"/None 表示输入舰船名检索与不进行额外检索直接 OCR 切换
        """
        assert self.legal(ships)
        assert flag_ship is None or flag_ship in ships
        self.timer.logger.debug(f'编队更改为：{ships}')
        self.detect()
        self._set_ships(ships, search_method=search_method)
        if order:
            self.reorder(ships)
        elif flag_ship is not None:
            position = self.ships.index(flag_ship)
            if position != 1:
                self.circular_move(position, 1)

    def reset(self):
        self.__init__(self.timer, self.fleet_id)
