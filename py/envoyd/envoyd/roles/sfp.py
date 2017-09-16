"""Static frontend proxy.

At the moment, one cluster is allocated per backend server.
"""

__all__ = [
    'sfp',
]

from collections import OrderedDict
from pathlib import Path
import json

from garage import cli

from envoyd.controllers import SupervisorInterface


class Supervisor(SupervisorInterface):

    PUBLIC_METHOD_NAMES = ()

    def __init__(self, *, args, envoy, envoy_args):

        self._done = False

        self._envoy = str(envoy.resolve())
        self._envoy_args = envoy_args

        self._frontends = OrderedDict()
        for name, address, port in args.frontend or ():
            self._frontends[name] = Frontend(address, int(port))

        for name, config_path in args.frontend_config or ():
            self._frontends[name].load_extra_config(Path(config_path))

        self._backends = OrderedDict()
        for name, address, port in args.backend or ():
            self._backends[name] = Backend(address, int(port))

        for name, config_path in args.backend_config or ():
            self._backends[name].load_extra_config(Path(config_path))

        for name, weight in args.backend_weight or ():
            self._backends[name].weight = int(weight)

    def __enter__(self):
        pass

    def __exit__(self, *_):
        pass

    def is_done(self):
        return self._done

    def spawn_default(self):
        pass

    def check_procs(self):
        pass

    def list_procs(self):
        pass


class ConfigBase:

    def __init__(self, address, port):
        self.address = address
        self.port = port
        self.extra_config = None

    def load_extra_config(self, config_path):
        with config_path.open() as config_file:
            self.extra_config = json.load(config_file)


class Frontend(ConfigBase):
    pass


class Backend(ConfigBase):

    def __init__(self, address, port):
        super().__init__(address, port)
        self.weight = 0


@cli.command('sfp')
@cli.argument(
    '--frontend',
    nargs=3, metavar=('NAME', 'ADDRESS', 'PORT'),
    action='append',
    help='add frontend to the proxy',
)
@cli.argument(
    '--frontend-config',
    nargs=2, metavar=('NAME', 'PATH'),
    action='append',
    help='set extra frontend config file to read from',
)
@cli.argument(
    '--backend',
    nargs=3, metavar=('NAME', 'ADDRESS', 'PORT'),
    action='append',
    help='add backend to the proxy',
)
@cli.argument(
    '--backend-config',
    nargs=2, metavar=('NAME', 'PATH'),
    action='append',
    help='set extra backend config file to read from',
)
@cli.argument(
    '--backend-weight',
    nargs=2, metavar=('NAME', 'WEIGHT'),
    action='append',
    help='set backend weight (range: [0, 100])',
)
@cli.defaults(make_supervisor=Supervisor)
def sfp(parser, args):

    # We use "role functions" to check command-line arguments.

    frontends = set(name for name, _, _ in args.frontend or ())
    if not frontends:
        parser.error('expect at least one frontend')

    backends = set(name for name, _, _ in args.backend or ())
    if not backends:
        parser.error('expect at least one backend')

    for name, path in args.frontend_config or ():

        if name not in frontends:
            parser.error('expect frontend %s' % name)

        if not Path(path).is_file():
            parser.error(
                'expect a existing config file for frontend %s: %s' %
                (name, path)
            )

    for name, path in args.backend_config or ():

        if name not in backends:
            parser.error('expect backend %s' % name)

        if not Path(path).is_file():
            parser.error(
                'expect a existing config file for backend %s: %s' %
                (name, path)
            )

    total_weight = 0

    for name, weight in args.backend_weight or ():

        if name not in backends:
            parser.error('expect backend %s' % name)

        try:
            weight = int(weight)
        except ValueError:
            parser.error(
                'expect integral weight value for backend %s: %s' %
                (name, weight)
            )

        if not 0 <= weight <= 100:
            parser.error(
                'expect weight range [0, 100] for backend %s: %s' %
                (name, weight)
            )

        total_weight += weight

    if total_weight != 100:
        parser.error('expect total weight to be 100, not %d' % total_weight)
