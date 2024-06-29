import os
import logging
from logging import Formatter, getLogger
from logging.handlers import RotatingFileHandler


class BaseLogger:
    def __init__(self, name: str = 'bot', log_path: str = './.logs/', filename: str = 'bot.log', level: int = logging.INFO, encoding: str = 'utf-8', maxBytes: int = 10 * 1024 * 1024, backupCount: int = 5):
        if not os.path.exists(log_path):
            os.makedirs(log_path)

        self._handler = RotatingFileHandler(
            filename=log_path + filename,
            encoding=encoding,
            maxBytes=maxBytes,
            backupCount=backupCount,
        )
        self._handler.setFormatter(Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', '%Y-%m-%d %H:%M:%S', style='{'))
        
        self.logger = getLogger(name)
        self.logger.addHandler(self._handler)
        self.logger.setLevel(level) # logging.INFO passes all levels except debug


class DiscordLogger(BaseLogger):
    def __init__(self, log_path: str = './.logs/', filename: str = 'discord.log', level: int = logging.INFO, encoding: str = 'utf-8', maxBytes: int = 10 * 1024 * 1024, backupCount: int = 5):
        super().__init__('discord', log_path, filename, level, encoding, maxBytes, backupCount)


class YoutubeDLLogger(BaseLogger):
    def __init__(self, name: str = 'yt-dlp', log_path: str = './.logs/', filename: str = 'yt_dlp.log', level: int = logging.INFO, encoding: str = 'utf-8', maxBytes: int = 10 * 1024 * 1024, backupCount: int = 5):
        super().__init__(name, log_path, filename, level, encoding, maxBytes, backupCount)

    def debug(self, msg):
        # For compatibility with youtube-dl, both debug and info are passed into debug
        # You can distinguish them by the prefix '[debug] '
        if msg.startswith('[debug] '):
            self.logger.debug(msg[8:])
        else:
            self.info(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

