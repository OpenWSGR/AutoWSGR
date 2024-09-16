from typing import Iterable


def remove_0_value_from_dict(d: dict):
    rd = {}
    for key, value in d.items():
        if value != 0 and value != None:
            rd[key] = value
    return rd


def unzip_element(o: object):
    if not isinstance(o, Iterable):
        return [o]
    res = []
    for value in o:
        if isinstance(value, (list, set)):
            res += unzip_element(value)
        else:
            res.append(value)
    return res


def unorder_equal(o1: Iterable, o2: Iterable, skip=[None]):
    if skip is None:
        skip = []
    return (set(o1) - set(skip)) == (set(o2) - set(skip))
