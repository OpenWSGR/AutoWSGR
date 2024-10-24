from collections.abc import Iterable
from typing import Any


def remove_0_value_from_dict(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v != 0}


def unzip_element(o: object) -> list[object] | Any | list:
    if not isinstance(o, Iterable):
        return [o]
    res = []
    for value in o:
        if isinstance(value, list | set):
            res += unzip_element(value)
        else:
            res.append(value)
    return res


def unorder_equal(o1: Iterable, o2: Iterable, skip=None) -> bool:
    if skip is None:
        skip = [None]
    return (set(o1) - set(skip)) == (set(o2) - set(skip))
