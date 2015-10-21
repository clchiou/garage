__all__ = [
    'LogReporterComponent',
]

import logging

from garage import components
from garage import metry
from garage.argparse import add_bool_argument
from garage.metry.reporters import logging as reporters_logging
from garage.metry.reporters.logging import LogReporter

from garage.startups.metry import MetryComponent


class LogReporterComponent(components.Component):

    require = components.ARGS

    provide = MetryComponent.require.metry_reporters

    def add_arguments(self, parser):
        group = parser.add_argument_group(reporters_logging.__name__)
        add_bool_argument(
            group, '--metry-log-reporter', default=False,
            help="""enable metry log reporter (default to %(default)s)""")

    def make(self, require):
        if require.args.metry_log_reporter:
            metry.add_reporter(
                LogReporter(logging.getLogger(reporters_logging.__name__)))
