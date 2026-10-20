import logging
import logging.handlers
import os

LOG_DIR = os.path.join(os.path.expanduser("~"), "FusionDFM", "logs")
LOG_FILE = os.path.join(LOG_DIR, "fusion_dfm.log")


def get_logger() -> logging.Logger:
    log = logging.getLogger("fusion_dfm")
    if not log.handlers:
        log.setLevel(logging.INFO)
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            h = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=512_000, backupCount=2, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(h)
        except OSError:
            log.addHandler(logging.NullHandler())
    return log
