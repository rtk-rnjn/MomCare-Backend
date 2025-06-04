from __future__ import annotations

import logging
import logging.handlers
from collections import deque, namedtuple
from datetime import datetime
from typing import Iterable

from pytz import timezone

filehandler = logging.handlers.RotatingFileHandler(
    "logs/log.log",
    maxBytes=1024 * 1024 * 5,
    mode="w",
    backupCount=5,
    encoding="utf-8",
)
filehandler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s")
filehandler.setFormatter(formatter)


class Record(namedtuple("Record", ["time", "name", "levelname", "msg"])):
    """
    A simple named tuple to represent a log record.
    """

    def __str__(self):
        return f"{self.time} - {self.name} - {self.levelname} - {self.msg}"

    def __repr__(self):
        return self.__str__()


class CustomLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(filehandler)

        self._recent_logs = deque(maxlen=1024)

    def debug(self, *args, **kwargs):
        self.logger.debug(*args, **kwargs)
        self._recent_logs.append((datetime.now(timezone("Asia/Kolkata")), "debug", args, kwargs))

    def info(self, *args, **kwargs):
        self.logger.info(*args, **kwargs)
        self._recent_logs.append((datetime.now(timezone("Asia/Kolkata")), "info", args, kwargs))

    def warning(self, *args, **kwargs):
        self.logger.warning(*args, **kwargs)
        self._recent_logs.append((datetime.now(timezone("Asia/Kolkata")), "warning", args, kwargs))

    def error(self, *args, **kwargs):
        self.logger.error(*args, **kwargs)
        self._recent_logs.append((datetime.now(timezone("Asia/Kolkata")), "error", args, kwargs))

    def critical(self, *args, **kwargs):
        self.logger.critical(*args, **kwargs)
        self._recent_logs.append((datetime.now(timezone("Asia/Kolkata")), "critical", args, kwargs))

    @property
    def recent_logs(self) -> Iterable[Record]:
        """
        Returns the most recent logs.
        """
        for time, level, args, kwargs in self._recent_logs:
            formatted_message = self.logger.makeRecord(
                self.logger.name,
                getattr(logging, level.upper()),
                fn="",
                lno=0,
                msg=args[0] if args else "",
                args=args[1:],
                exc_info=kwargs.get("exc_info", None),
            )
            yield Record(time=time, name=formatted_message.name, levelname=formatted_message.levelname, msg=formatted_message.getMessage())


def get_logger(name: str) -> CustomLogger:
    """
    Returns a CustomLogger instance for the given name.
    """
    return CustomLogger(name)


log = get_logger("app")
