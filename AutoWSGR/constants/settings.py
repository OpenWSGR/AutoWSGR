class Settings():
    LDPLAYER_ROOT = "C:\leidian\LDPlayer9"
    LOG_PATH = "log"
    DELAY = 2

    device_name = "emulator-5554"
    account = None
    password = None

    DEBUG = False
    SHOW_MAP_NODE = False
    SHOW_ANDROID_INPUT = False
    SHOW_ENEMY_RUELS = False
    SHOW_FIGHT_STAGE = False
    SHOW_CHAPTER_INFO = False
    SHOW_MATCH_FIGHT_STAGE = False

    def __init__(self):
        pass


S = Settings()


def show_all_debug_info():
    global S
    S.SHOW_MATCH_FIGHT_STAGE = True
    S.SHOW_MAP_NODE = True
    S.SHOW_ANDROID_INPUT = True
    S.SHOW_ENEMY_RUELS = True
    S.SHOW_FIGHT_STAGE = True
    S.SHOW_CHAPTER_INFO = True
    S.DEBUG = True
