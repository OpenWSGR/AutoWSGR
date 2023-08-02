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
    for obj in o1:
        if obj not in o2 and obj not in skip:
            return False
    for obj in o2:
        if obj not in o1 and obj not in skip:
            return False
    return True
