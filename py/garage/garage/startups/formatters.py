__all__ = [
    'FormatterComponent',
]

from garage import asserts
from garage import components
from garage import formatters


class FormatterComponent(components.Component):

    require = components.ARGS

    provide = components.make_fqname_tuple(__name__, 'formatter')

    def add_arguments(self, parser):
        group = parser.add_argument_group(formatters.__name__)
        group.add_argument(
            '--output-format', default='yaml', choices=('json', 'yaml'),
            help="""set output format (default to %(default)s)""")

    def make(self, require):
        args = require.args
        if args.output_format == 'json':
            return formatters.make_json_formatter()
        elif args.output_format == 'yaml':
            return formatters.make_yaml_formatter()
        else:
            asserts.fail('cannot recognize output format %r' %
                         args.output_format)
