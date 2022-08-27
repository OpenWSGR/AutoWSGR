import copy
import time

import yaml
from api import ClickImage, ImagesExist, UpdateScreen, click
from constants import FIGHT_CONDITIONS_POSITON, FightImage, identify_images
from game import (ConfirmOperation, DetectShipStatu, GetEnemyCondition,
                  MoveTeam, QuickRepair, UpdateShipPoint, UpdateShipPosition,
                  change_fight_map, goto_game_page, identify_page,
                  process_bad_network)
from supports import SymbolImage, Timer
from utils.io import recursive_dict_update

from .common import FightInfo, FightPlan, NodeLevelDecisionBlock, Ship