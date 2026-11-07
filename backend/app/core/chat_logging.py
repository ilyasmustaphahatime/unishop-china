"""Prevent rejected URL credentials and protocol debug frames entering logs."""
import logging


class ChatTransportLogFilter(logging.Filter):
    def filter(self, record):
        if record.levelno < logging.INFO:
            return False
        values = record.args if isinstance(record.args, tuple) else (record.args,)
        if any(isinstance(value, str) and "/chat" in value for value in (*values, record.msg)):
            return False
        if record.exc_info and record.module in {"websockets_sansio_impl", "websockets_impl", "wsproto_impl"}:
            record.msg, record.args = "WebSocket protocol error.", ()
            record.exc_info = record.exc_text = None
        return True


def install_chat_log_protection() -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi",
                 "websockets", "websockets.server", "websockets.client"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, ChatTransportLogFilter) for item in logger.filters):
            logger.addFilter(ChatTransportLogFilter())
