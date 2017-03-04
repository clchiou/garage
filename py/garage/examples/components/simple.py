import argparse
import logging
import sys
from contextlib import ExitStack

from startup import startup

from garage import components
from garage.startups.logging import LoggingComponent
from garage.startups.multiprocessing import Python2Component
from garage.startups.threads.executors import ExecutorComponent


def main(argv):
    startup.set(components.PARSER, argparse.ArgumentParser(
        description="""Simple command."""
    ))

    components.bind(ExecutorComponent())
    components.bind(LoggingComponent())
    components.bind(Python2Component())

    def real_main(args):
        logging.info('complete')
        return 0

    with ExitStack() as exit_stack:
        startup.set(components.MAIN, real_main)
        startup.set(components.EXIT_STACK, exit_stack)
        return components.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
