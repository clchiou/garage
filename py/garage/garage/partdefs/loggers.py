import enum
import logging
import typing

from garage import apps
from garage import parameters
from garage import parts


@enum.unique
class LogLevel(enum.Enum):
    NOTSET = logging.NOTSET
    TRACE = apps.TRACE
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


PARTS = parts.PartList('garage.loggers', [
    ('set_logging_levels', parts.AUTO),
])


PARAMS = parameters.define_namespace(
    'garage.loggers',
    'configure loggers',
)
PARAMS.logging_level = parameters.create(
    (), type=typing.List[typing.Tuple[str, LogLevel]],
    doc='set logging level of logger',
)


@parts.define_maker
def set_logging_levels() -> PARTS.set_logging_levels:
    for logger_name, logging_level in PARAMS.logging_level.get():
        logging.getLogger(logger_name).setLevel(logging_level.value)
