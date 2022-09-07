from functools import wraps

import constants.global_attributes as Globals


def try_for_times(fun):
    @wraps(fun)
    def imtemplate(*arg, **kwargs):
        if (Globals.script_end == 1):
            return
        for i in range(2):
            try:
                return fun(*arg, **kwargs)
            except:
                pass
        return fun(*arg, **kwargs)

    return imtemplate


def stopper(fun):
    @wraps(fun)
    def imtemplate(*arg, **kwargs):
        return 'end' if (Globals.script_end == 1) else fun(*arg, **kwargs)

    return imtemplate
