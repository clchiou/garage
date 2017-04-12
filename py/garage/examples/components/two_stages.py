import argparse
import logging
import sys
from contextlib import ExitStack

from startup import Startup, startup

from garage import components
from garage.startups.logging import LoggingComponent
from garage.startups.multiprocessing import Python2Component
from garage.startups.threads.executors import ExecutorComponent


def main(argv):
    startup.set(components.PARSER, argparse.ArgumentParser(
        description="""Two stage command."""
    ))

    component_startup = Startup()

    comps = (
        ExecutorComponent(),
        LoggingComponent(),
        Python2Component(),
    )
    for comp in comps:
        components.bind(comp, next_startup=component_startup)

    def real_main(args):
        with ExitStack() as exit_stack:
            component_startup.set(components.ARGS, args)
            component_startup.set(components.EXIT_STACK, exit_stack)
            component_startup(components.check_args)
            component_startup.call()
            logging.info('complete')
        return 0

    startup.set(components.MAIN, real_main)
    return components.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
