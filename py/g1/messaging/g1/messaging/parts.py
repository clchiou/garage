import g1.asyncs.servers.parts
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from .reqrep import servers

SERVER_LABEL_NAMES = (
    'server_params',
    'server',
)


def define_server(module_path=None, **kwargs):
    module_path = module_path or servers.__name__
    module_labels = labels.make_labels(module_path, *SERVER_LABEL_NAMES)
    setup_server(
        module_labels,
        parameters.define(module_path, make_server_params(**kwargs)),
    )
    return module_labels


def setup_server(module_labels, module_params):
    utils.depend_parameter_for(module_labels.server_params, module_params)
    utils.define_maker(
        make_server,
        {
            'params': module_labels.server_params,
            'server': module_labels.server,
        },
    )
    utils.define_binder(
        on_graceful_exit,
        g1.asyncs.servers.parts.LABELS.serve,
        {
            'server': module_labels.server,
        },
    )


def make_server_params(url=None, parallelism=1):
    return parameters.Namespace(
        'make server socket',
        url=parameters.make_parameter(url, str, 'url that server listens on'),
        parallelism=parameters.Parameter(
            parallelism,
            'number of server tasks',
            type=int,
            validate=(0).__lt__,
        ),
    )


def make_server(params, server) -> g1.asyncs.servers.parts.LABELS.serve:
    server.socket.listen(params.url.get())
    return servers.run_server(server, parallelism=params.parallelism.get())


async def on_graceful_exit(
    graceful_exit: g1.asyncs.servers.parts.LABELS.graceful_exit,
    server,
):
    await graceful_exit.wait()
    server.socket.close()
