import os
import logging
from logging import Formatter, Logger, getLogger
from logging.handlers import RotatingFileHandler


LOG_PATH = './.logs/'

# logging.INFO passes all levels except debug

def _create_handler(log_path: str, filename: str, encoding: str = 'utf-8', max_bytes: int = 100 * 1024, backup_count: int = 5) -> RotatingFileHandler:
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    
    handler = RotatingFileHandler(
        filename=log_path + filename,
        encoding=encoding,
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    handler.setFormatter(Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', '%Y-%m-%d %H:%M:%S', style='{'))
    
    return handler


class YoutubeDLLogger(Logger):
    def __init__(self, name: str, level: int):
        super().__init__(name, level)

    def debug(self, msg: str, *args, **kwargs) -> None:
        # For compatibility with youtube-dl, both debug and info are passed into debug
        # You can distinguish them by the prefix '[debug] '
        if msg.startswith('[debug] '):
            super().debug(msg, *args, **kwargs)
        else:
            self.info(msg, *args, **kwargs)


def get_base_logger(name: str = 'bot', level: int = logging.INFO, log_path: str = LOG_PATH) -> Logger:
    logger = Logger(name, level)
    logger.addHandler(_create_handler(log_path, name + '.log'))
    return logger


def get_ytdl_logger(name: str = 'yt_dl', level: int = logging.INFO, log_path: str = LOG_PATH) -> YoutubeDLLogger:
    logger = YoutubeDLLogger(name, level)
    logger.addHandler(_create_handler(log_path, name + '.log'))
    return logger


def setup_discord_logger(level: int = logging.INFO, log_path: str = LOG_PATH) -> None:
    logger = getLogger('discord')
    logger.setLevel(level)
    logger.addHandler(_create_handler(log_path, 'discord.log'))

