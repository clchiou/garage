"""Initialize garage.spiders."""

__all__ = [
    'SPIDER',
    'SPIDER_PARSER',
    'init'
]

from startup import startup

import garage.spiders
from garage.functools import run_once
from garage.spiders import Spider

from garage.startups import ARGS, PARSE, PARSER
from garage.startups import components
from garage.startups.http import CLIENT


SPIDER = __name__ + ':spider'
SPIDER_PARSER = __name__ + ':spider_parser'


NUM_SPIDERS = 8


def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(garage.spiders.__name__)
    group.add_argument(
        '--num-spiders', default=NUM_SPIDERS, type=int,
        help="""set number of spiders (default to %(default)s)""")


def make_spider(args: ARGS, parser: SPIDER_PARSER, client: CLIENT) -> SPIDER:
    return Spider(parser=parser, num_spiders=args.num_spiders, client=client)


@run_once
def init():
    startup(add_arguments)
    components.startup(make_spider)
