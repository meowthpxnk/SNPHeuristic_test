import logging
import logging.config

from app.utils import read_yaml

LOGGING_CONFIG = read_yaml("config/logging.yaml")
logging.config.dictConfig(LOGGING_CONFIG)
