from os.path import dirname
import os

DATA_ROOT = os.path.join(dirname(dirname(__file__)),"data")
IMG_ROOT = os.path.join(DATA_ROOT, "images")
MAP_ROOT = os.path.join(DATA_ROOT, "map")
PLAN_ROOT = os.path.join(DATA_ROOT, "plans")
SETTING_ROOT = os.path.join(DATA_ROOT, "settings")
BIN_ROOT = os.path.join(dirname(dirname(DATA_ROOT)), "bin")
TUNNEL_ROOT = os.path.join(BIN_ROOT, 'image_recognize')
ADB_ROOT = os.path.join(BIN_ROOT, 'adb')