__all__ = [
    'Python2Component',
]

from garage import components
from garage import multiprocessing


class Python2Component(components.Component):

    require = (components.ARGS, components.EXIT_STACK)

    provide = components.make_fqname_tuple(__name__, 'python2')

    def add_arguments(self, parser):
        group = parser.add_argument_group(multiprocessing.__name__)
        group.add_argument(
            '--python2', default='python2',
            help="""set path or command name of python2 executable""")
        group.add_argument(
            '--python2-max-workers', type=int, default=8,
            help="""set max concurrent python2 worker threads
                    (default to %(default)s)
                 """)

    def make(self, require):
        args, exit_stack = require.args, require.exit_stack
        return exit_stack.enter_context(multiprocessing.python(
            executable=args.python2,
            max_workers=args.python2_max_workers,
        ))
