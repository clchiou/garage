"""Initialize modules with 2-stages of startup.

The first startup is the normal, global startup object.  It is called
before main(), which will parse command-line arguments and it will
resolve MAIN and ARGS.  Its dependency graph is:

  PARSER ---> PARSE --+--> ARGS
                      |
              ARGV ---+

  MAIN

The second startup is components.startup, which is called lazily when
you access to any component.  You may use the second stage startup to
initialize "heavy" objects (i.e., components) such as database
connection.

Note that the second stage startup will "inherit" all resolved values
of the first stage startup so that you may reference them.
"""

__all__ = [
    'ARGS',
    'ARGV',
    'MAIN',
    'PARSE',
    'PARSER',

    'EXIT_STACK',

    'components',
    'main',
]

from startup import Startup, startup

from garage.collections import FixedNamespace


# These are used in the first stage startup.
ARGS = 'args'
ARGV = 'argv'
MAIN = 'main'
PARSE = 'parse'
PARSER = 'parser'


# This is optional in the second stage startup but very useful when you
# need to manage contexts of objects.
EXIT_STACK = 'exit_stack'


class LazyStartup:

    def __init__(self):
        self.startup = Startup()
        self._variables = None
        self._vars = None

    @property
    def variables(self):
        if self._variables is None:
            self._variables = self.startup.call()
            del self.startup
        return self._variables

    @property
    def vars(self):
        if self._vars is None:
            self._vars = FixedNamespace(**{
                name[name.rfind(':')+1:]: value
                for name, value in self.variables.items()
            })
        return self._vars


components = LazyStartup()


def parse_argv(parser: PARSER, argv: ARGV, _: PARSE) -> ARGS:
    return parser.parse_args(argv[1:])


def main(argv):
    # Make sure components.vars has not been assessed yet.
    assert hasattr(components, 'startup')
    startup(parse_argv)
    variables = startup.call(argv=argv)
    for name, value in variables.items():
        components.startup.set(name, value)
    return variables[MAIN](variables[ARGS])
