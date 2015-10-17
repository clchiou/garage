__all__ = [
    'LogReporter',
]

import logging


LOG_FORMAT = '%s:%s=%r'


class LogReporter:

    def __init__(self, logger, level=logging.INFO, log_format=LOG_FORMAT):
        self.logger = logger
        self.level = level
        self.log_format = log_format

    def __call__(self, metry_name, measure_name, measurement):
        self.logger.log(
            self.level, self.log_format, metry_name, measure_name, measurement)
