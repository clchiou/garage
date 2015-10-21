__all__ = [
    'MetryComponent',
]

from garage import components
from garage import metry
from garage.argparse import add_bool_argument


class MetryComponent(components.Component):

    require = components.make_fqname_tuple(
        __name__,
        components.ARGS,
        'metry_reporters',
    )

    def add_arguments(self, parser):
        group = parser.add_argument_group(metry.__name__)
        add_bool_argument(
            group, '--metry', default=False,
            help="""enable metry (default to %(default)s)""")

    def make(self, require):
        if require.args.metry:
            metry.enable()
            metry.initialize()
