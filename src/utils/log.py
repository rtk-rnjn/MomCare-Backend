import logging
import logging.handlers

log = logging.getLogger(__name__)
filehandler = logging.handlers.RotatingFileHandler(
    "logs/log.log",
    maxBytes=1024 * 1024 * 5,
    mode="a",
)
filehandler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s")
filehandler.setFormatter(formatter)
log.addHandler(filehandler)
log.setLevel(logging.DEBUG)
