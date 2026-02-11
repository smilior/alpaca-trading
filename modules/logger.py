"""構造化ロギング + ローテーション。

JSON Lines形式でログを出力し、RotatingFileHandlerで10MB x 5世代管理。
コンソールにはWARNING以上のみ出力する。
"""

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    """JSON Lines形式のログフォーマッター。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "module": record.module,
            "func": record.funcName,
            "exec_id": getattr(record, "exec_id", None),
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logger(
    log_dir: str = "logs",
    log_file: str = "agent.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """アプリケーションロガーを設定する。

    Args:
        log_dir: ログ出力ディレクトリ
        log_file: ログファイル名
        max_bytes: ローテーションサイズ（バイト）
        backup_count: 保持世代数

    Returns:
        設定済みのLogger
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("trading_agent")
    logger.setLevel(logging.DEBUG)

    # 既存のハンドラをクリア（重複防止）
    logger.handlers.clear()

    # ファイルハンドラ: JSON Lines, DEBUG以上
    file_handler = RotatingFileHandler(
        filename=str(log_path / log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    # コンソールハンドラ: WARNING以上のみ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(module)s: %(message)s")
    )
    logger.addHandler(console_handler)

    return logger


def get_logger() -> logging.Logger:
    """既存のロガーを取得する。未設定の場合はデフォルトで初期化。"""
    logger = logging.getLogger("trading_agent")
    if not logger.handlers:
        return setup_logger()
    return logger
