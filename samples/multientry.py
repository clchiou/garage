import argparse
import logging
import sys
from contextlib import ExitStack
from functools import partial

from startup import Startup, startup

from garage import components
from garage.startups.http import HttpComponent
from garage.startups.logging import LoggingComponent
from garage.startups.multiprocessing import Python2Component
from garage.startups.threads.executors import ExecutorComponent


def main(argv):
    parser = argparse.ArgumentParser(description="""Multi-entry command.""")
    parser.set_defaults(cmd=None)
    startup.set(components.PARSER, parser)

    component_startups = {}
    subparsers = parser.add_subparsers(title='commands')
    for cmd in ('A', 'B', 'C'):
        component_startup = Startup()
        component_startups[cmd] = component_startup
        parser_ = '%s:cmd_%s_parser' % (__name__, cmd.lower())
        subparser = subparsers.add_parser(cmd)
        subparser.set_defaults(cmd=cmd)
        startup.set(parser_, subparser)
        comps = (
            ExecutorComponent(),
            HttpComponent(),
            LoggingComponent(),
            Python2Component(),
        )
        for comp in comps:
            components.bind(
                comp,
                component_startup=component_startup,
                parser_=parser_,
            )

    def real_main(args, component_startup):
        with ExitStack() as exit_stack:
            component_startup.set(components.ARGS, args)
            component_startup.set(components.EXIT_STACK, exit_stack)
            component_startup.call()
            logging.info('complete of command %s', args.cmd)
        return 0

    @startup
    def select_main(
            parser: components.PARSER,
            args: components.ARGS,
        ) -> components.MAIN:
        if not args.cmd:
            parser.error('command is required')
        component_startup = component_startups[args.cmd]
        return partial(real_main, component_startup=component_startup)

    return components.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
