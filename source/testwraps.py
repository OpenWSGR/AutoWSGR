import logging
# from logging import handlers
from logging import FileHandler, StreamHandler  
# FileHandler和StreamHandler分别对应将日志输出到文档、控制台
 
log = logging.getLogger()
handler = logging.StreamHandler()
handler2 = logging.FileHandler("log.txt")
log.addHandler(handler)
log.addHandler(handler2)
log.setLevel(logging.INFO)

log.info("这是INFO-1")
