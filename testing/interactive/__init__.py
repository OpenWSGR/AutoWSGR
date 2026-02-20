"""交互式端到端测试脚本集合。

这些脚本可直接作为命令行程序运行（无需测试框架），
适合快速验证完整操作流程。

特点:
- 默认输出 DEBUG 级别日志
- 自动检测并连接设备
- 直接运行对应的 ops，打印汇总结果

用法示例::

    python testing/interactive/campaign.py
    python testing/interactive/campaign.py 127.0.0.1:16384 困难航母 3
"""
