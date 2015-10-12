__all__ = [
    'LoggingComponent',
]

import logging
import threading

import garage
from garage import components


class LoggingComponent(components.Component):

    TRACE = logging.DEBUG - 1

    LOG_FORMAT = (
        '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'
    )

    require = components.ARGS

    def __init__(self, verbose=0):
        self.verbose = verbose

    def add_arguments(self, parser):
        group = parser.add_argument_group(garage.__name__)
        group.add_argument(
            '-v', '--verbose', action='count', default=self.verbose,
            help='verbose output')

    def make(self, require):
        args = require.args
        logging.addLevelName(self.TRACE, 'TRACE')
        if args.verbose == 0:
            level = logging.WARNING
        elif args.verbose == 1:
            level = logging.INFO
        elif args.verbose == 2:
            level = logging.DEBUG
        else:
            level = self.TRACE
        logging.basicConfig(level=level, format=self.LOG_FORMAT)
        threading.current_thread().name = garage.__name__ + '#main'

    # Hack for manipulating startup order.
    add_arguments.__module__ = garage.__name__
    make.__module__ = garage.__name__
