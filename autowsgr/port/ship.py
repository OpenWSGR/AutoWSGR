import os
from typing import Iterable

from autowsgr.constants.data_roots import OCR_ROOT
from autowsgr.constants.image_templates import IMG
from autowsgr.constants.positions import FLEET_POSITION
from autowsgr.game.game_operation import MoveTeam
from autowsgr.timer import Timer
from autowsgr.utils.api_image import absolute_to_relative, crop_image
from autowsgr.utils.io import recursive_dict_update, yaml_to_dict
from autowsgr.utils.operator import unorder_equal

POS = yaml_to_dict(os.path.join(OCR_ROOT, "relative_location.yaml"))


def count_ship(fleet):
    res = sum(have_ship(fleet[i]) for i in range(1, min(len(fleet), 7)))
    return res


def have_ship(ship):
    return ship is not None and ship != ""


class Ship:
    pass


class Fleet:
    def __init__(self, timer: Timer, fleet_id=None):
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

    def __eq__(self, other: object):
        if not isinstance(other, (Iterable, Fleet)):
            raise ValueError()
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

    def detect(self):
        """在对应的战斗准备页面检查舰船"""
        assert self.timer.wait_image(IMG.identify_images["fight_prepare_page"]) != False
        if self.fleet_id is not None:
            MoveTeam(self.timer, self.fleet_id)
        ships = self.timer.recognize_ship(
            self.timer.get_screen()[433:459], self.timer.ship_names
        )
        self.ships = [None] * 7
        for rk, ship in enumerate(ships):
            self.ships[rk + 1] = ship[1]

    def change_ship(self, position, ship_name, search_method="word"):
        self.ships[position] = ship_name
        self.timer.click(*FLEET_POSITION[position], delay=0)
        res = self.timer.wait_images(
            IMG.choose_ship_image[1:3] + [IMG.choose_ship_image[4]],
            after_get_delay=0.4,
            gap=0,
            timeout=16,
        )
        if res == None:
            raise TimeoutError("选择舰船时点击超时")
        if ship_name is None:
            self.timer.click(83, 167, delay=0)
        else:
            if res == 1:
                self.timer.relative_click(0.875, 0.246)
            if search_method == "word":
                self.timer.relative_click(0.729, 0.056, delay=0)
                self.timer.wait_image(
                    IMG.choose_ship_image[3], gap=0, after_get_delay=0.1
                )
                self.timer.text(ship_name)
                self.timer.click(1219 * 0.75, 667 * 0.75, delay=1)

            ships = self.timer.recognize_ship(
                self.timer.get_screen()[:, :1048], self.timer.ship_names
            )
            self.timer.logger.info("当前页面中舰船：", ships)
            for ship in ships:
                if ship[1] == ship_name:
                    rel_center = absolute_to_relative(ship[0], (1280, 720))
                    self.timer.relative_click(*rel_center)
                    break

        self.timer.wait_pages("fight_prepare_page", gap=0)

    def _set_ships(self, ships, search_method="word"):
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
            self.change_ship(position, ship, search_method=search_method)
            ok[position] = True

        for i in range(1, 7):
            if ok[7 - i] == False and self.ships[7 - i] != None:
                self.change_ship(7 - i, None)
                self.ships[7 - i :] = self.ships[8 - i :]

    def reorder(self, ships):
        assert unorder_equal(ships, self.ships, skip=[None, ""])
        for i in range(1, 7):
            ship = ships[i]
            if not have_ship(ship):
                return
            if self.ships[i] != ship:
                self.circular_move(self.ships.index(ship), i)

    def circular_move(self, p1, p2):
        if p1 > p2:
            self.ships = (
                self.ships[:p2]
                + self.ships[p1 : p1 + 1]
                + self.ships[p2:p1]
                + self.ships[p1 + 1 :]
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
        if len(ships) <= 7:
            ships += [None] * 7
        for i in range(1, 7):
            if ships[i] is None:
                ok = True
            if ok and ships[i] is not None:
                return False
        return True

    def set_ship(self, ships, flag_ship=None, order=False, search_method="word"):
        """设置指定位置的舰队, 1-index
        Args:
            ships (list(str)): 代表舰船 [0号位留空, 1号位, 2号位, ...]
            flag_ship: 如果不为 None, 则代表旗舰名称
            order (bool): 是否按照 ships 给定的顺序 (优先级高于旗舰指定)
        """
        assert self.legal(ships)
        assert flag_ship is None or flag_ship in ships
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
