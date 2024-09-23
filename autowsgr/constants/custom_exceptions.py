class ImageNotFoundErr(BaseException):
    def __init__(self, *args: object):
        super().__init__(*args)


class NetworkErr(BaseException):
    def __init__(self, *args: object):
        super().__init__(*args)


class ShipNotFoundErr(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class CriticalErr(BaseException):
    """严重错误
    通常发生严重错误表明实现有重大问题
    Args:
        BaseException (_type_): _description_
    """

    def __init__(self, *args: object):
        super().__init__(*args)


class LogitException(BaseException):
    def __init__(self, *args: object):
        super().__init__()(*args)
