from types import SimpleNamespace
from utils.io import yaml_to_dict

S = SimpleNamespace()
user_settings = yaml_to_dict("data/settings/settings.yaml")
S.__dict__.update(user_settings)

def show_all_debug_info():

    S.SHOW_MATCH_FIGHT_STAGE = True
    S.SHOW_MAP_NODE = True
    S.SHOW_ANDROID_INPUT = True
    S.SHOW_ENEMY_RUELS = True
    S.SHOW_FIGHT_STAGE = True
    S.SHOW_CHAPTER_INFO = True
    S.DEBUG = True
    
