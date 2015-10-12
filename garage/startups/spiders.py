"""Initialize garage.spiders."""

__all__ = [
    'SpiderComponent',
]

import garage.spiders
from garage import components
from garage.spiders import Spider

from garage.startups.http import HttpComponent


class SpiderComponent(components.Component):

    NUM_SPIDERS = 8

    require = components.make_fqname_tuple(
        __name__,
        components.ARGS,
        HttpComponent.provide.client,
        'spider_parser',
    )

    provide = components.make_fqname_tuple(__name__, 'spider')

    def add_arguments(self, parser):
        group = parser.add_argument_group(garage.spiders.__name__)
        group.add_argument(
            '--num-spiders', default=self.NUM_SPIDERS, type=int,
            help="""set number of spiders (default to %(default)s)""")

    def make(self, require):
        return Spider(
            parser=require.spider_parser,
            num_spiders=require.args.num_spiders,
            client=require.client,
        )
