from functools import wraps
from constants.global_attribute import script_end



def try_for_times(fun):
    @wraps(fun)
    def imtemplate(*arg, **kwargs):
        if (script_end == 1):
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
        return 'end' if (script_end == 1) else fun(*arg, **kwargs)

    return imtemplate
