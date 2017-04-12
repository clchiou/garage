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
    parser = argparse.ArgumentParser(description="""Multi-entry command.""")
    parser.set_defaults(next_main=None, next_startup=None, cmd=None)
    startup.set(components.PARSER, parser)

    subparsers = parser.add_subparsers(title='commands')
    for cmd in ('A', 'B', 'C'):
        next_startup = Startup()
        parser_ = '%s:cmd_%s_parser' % (__name__, cmd.lower())
        subparser = subparsers.add_parser(cmd)
        subparser.set_defaults(
            next_main=next_main, next_startup=next_startup, cmd=cmd)
        startup.set(parser_, subparser)
        comps = (
            ExecutorComponent(),
            LoggingComponent(),
            Python2Component(),
        )
        for comp in comps:
            components.bind(
                comp,
                next_startup=next_startup,
                parser_=parser_,
            )

    @startup
    def select_main(
            parser: components.PARSER,
            args: components.ARGS,
        ) -> components.MAIN:
        if not args.next_main:
            parser.error('command is required')
        return args.next_main

    return components.main(argv)


def next_main(args):
    with ExitStack() as exit_stack:
        args.next_startup.set(components.ARGS, args)
        args.next_startup.set(components.EXIT_STACK, exit_stack)
        args.next_startup(components.check_args)
        args.next_startup.call()
        logging.info('complete of command %s', args.cmd)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
