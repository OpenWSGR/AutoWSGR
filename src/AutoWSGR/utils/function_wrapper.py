from functools import wraps

from AutoWSGR.constants.global_attribute import script_end


def try_for_times(error_processor=None):
    def _try_for_times(fun):
        @wraps(fun)
        def imtemplate(*arg, **kwargs):
            if script_end == 1:
                return
            for _ in range(3):
                try:
                    return fun(*arg, **kwargs)
                except:
                    if error_processor is not None:
                        res = error_processor()
                        print("error_identified", res)
                    else:
                        pass
                return fun(*arg, **kwargs)

        return imtemplate

    return _try_for_times


def stopper(fun):
    @wraps(fun)
    def imtemplate(*arg, **kwargs):
        return "end" if (script_end == 1) else fun(*arg, **kwargs)

    return imtemplate
