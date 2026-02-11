"""modules/logger.py のテスト。"""

import json
import logging
from pathlib import Path

from modules.logger import JsonFormatter, get_logger, setup_logger


class TestJsonFormatter:
    def test_format_basic(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="trading_agent",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["msg"] == "Test message"
        assert "ts" in data

    def test_format_with_exec_id(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="trading_agent",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Order submitted",
            args=(),
            exc_info=None,
        )
        record.exec_id = "2026-01-15_morning"  # type: ignore[attr-defined]
        output = formatter.format(record)
        data = json.loads(output)
        assert data["exec_id"] == "2026-01-15_morning"

    def test_format_with_exception(self) -> None:
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="trading_agent",
                level=logging.ERROR,
                pathname="test.py",
                lineno=10,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError" in data["exception"]


class TestSetupLogger:
    def test_creates_log_file(self, tmp_path: Path) -> None:
        log_dir = str(tmp_path / "logs")
        logger = setup_logger(log_dir=log_dir)
        logger.info("Test log entry")

        log_file = tmp_path / "logs" / "agent.log"
        assert log_file.exists()

        content = log_file.read_text()
        data = json.loads(content.strip())
        assert data["msg"] == "Test log entry"
        assert data["level"] == "INFO"

    def test_handler_levels(self, tmp_path: Path) -> None:
        log_dir = str(tmp_path / "logs")
        logger = setup_logger(log_dir=log_dir)

        # ファイルハンドラはDEBUG、コンソールはWARNING
        file_handler = None
        console_handler = None
        for h in logger.handlers:
            if hasattr(h, "baseFilename"):
                file_handler = h
            else:
                console_handler = h

        assert file_handler is not None
        assert file_handler.level == logging.DEBUG
        assert console_handler is not None
        assert console_handler.level == logging.WARNING

    def test_no_duplicate_handlers(self, tmp_path: Path) -> None:
        log_dir = str(tmp_path / "logs")
        setup_logger(log_dir=log_dir)
        logger = setup_logger(log_dir=log_dir)
        assert len(logger.handlers) == 2  # file + console

    def test_json_lines_format(self, tmp_path: Path) -> None:
        log_dir = str(tmp_path / "logs")
        logger = setup_logger(log_dir=log_dir)
        logger.info("Line 1")
        logger.warning("Line 2")

        log_file = tmp_path / "logs" / "agent.log"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "ts" in data
            assert "level" in data
            assert "msg" in data


class TestGetLogger:
    def test_returns_logger(self, tmp_path: Path) -> None:
        # まずセットアップ
        setup_logger(log_dir=str(tmp_path / "logs"))
        logger = get_logger()
        assert logger.name == "trading_agent"
        assert len(logger.handlers) > 0

    def test_auto_setup_if_no_handlers(self) -> None:
        # ハンドラをクリアしてからget_logger
        logger = logging.getLogger("trading_agent")
        logger.handlers.clear()
        logger = get_logger()
        assert len(logger.handlers) > 0
