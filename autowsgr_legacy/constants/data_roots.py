from os.path import dirname, join


DATA_ROOT = join(dirname(dirname(__file__)), 'data')
IMG_ROOT = join(DATA_ROOT, 'images')
MAP_ROOT = join(DATA_ROOT, 'map')
SETTING_ROOT = join(DATA_ROOT, 'settings')
OCR_ROOT = join(DATA_ROOT, 'ocr')

BIN_ROOT = join(dirname(DATA_ROOT), 'bin')
