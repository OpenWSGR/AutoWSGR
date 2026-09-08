"""E2E 快速实机验证工具包 (tools/e2e)。

用法::

    python tools/e2e/run.py --list                  # 列出全部验证 case
    python tools/e2e/run.py screenshot --no-launch  # 链路自检 (不动游戏)
    python tools/e2e/run.py normal_fight --with-ocr --plan 1-1 --times 1

新增加速验证: 在 cases/ 目录复制 template 改写 run() 即可, 无需改框架。
"""
