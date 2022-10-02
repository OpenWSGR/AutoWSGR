from os.path import dirname
import os

DATA_ROOT = os.path.join(dirname(dirname(__file__)),"data")
IMG_ROOT = os.path.join(DATA_ROOT, "images")
MAP_ROOT = os.path.join(DATA_ROOT, "map")
PLAN_ROOT = os.path.join(DATA_ROOT, "plans")
SETTING_ROOT = os.path.join(DATA_ROOT, "settings")
TUNNEL_ROOT = os.path.join(DATA_ROOT, "tunnel")