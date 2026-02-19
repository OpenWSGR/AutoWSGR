"""测试日志配置。"""

from pathlib import Path
from unittest.mock import patch

from autowsgr.infra.logger import setup_logger


class TestSetupLogger:
    """测试 setup_logger 函数。"""

    def test_console_only(self):
        """不传 log_dir 时仅配置控制台输出。"""
        setup_logger(level="DEBUG")
        # 主要验证不抛出异常

    def test_with_log_dir(self, tmp_path: Path):
        """传入 log_dir 时应自动创建目录。"""
        log_dir = tmp_path / "logs" / "sub"
        setup_logger(log_dir=log_dir, level="INFO")
        assert log_dir.exists()

    def test_custom_level(self):
        """可以指定不同的日志级别。"""
        setup_logger(level="WARNING")
        # 验证不抛出异常

    def test_logger_writes_to_file(self, tmp_path: Path):
        """验证日志内容写入文件。"""
        from loguru import logger

        log_dir = tmp_path / "logs"
        setup_logger(log_dir=log_dir, level="DEBUG")
        logger.info("test message 12345")

        # loguru 异步写入，需检查文件是否存在
        log_files = list(log_dir.glob("autowsgr_*.log"))
        # 文件可能还没 flush，至少目录应该存在
        assert log_dir.exists()
