"""E2E 验证 case 目录。

每个 *.py 是一个可独立运行的实机验证脚本, 约定:
- 必须: ``def run(rt) -> bool`` — 步骤主体 (rt 是 E2ERunner 基座)
- 可选: ``DESC: str`` — 一句话描述 (--list 显示)
- 可选: ``def add_arguments(parser)`` — case 专属命令行参数

新增验证: 复制任意示例文件改写 run() 即可, 框架自动发现。
"""
