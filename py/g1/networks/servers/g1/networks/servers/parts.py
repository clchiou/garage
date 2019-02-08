from g1.apps import asyncs
from g1.apps import parameters
from g1.networks import servers


def make_server_socket_params(
    *,
    host='',
    port=0,
    reuse_address=False,
    reuse_port=False,
):
    return parameters.Namespace(
        'make server socket',
        host=parameters.Parameter(host),
        port=parameters.Parameter(port),
        reuse_address=parameters.Parameter(reuse_address),
        reuse_port=parameters.Parameter(reuse_port),
    )


def make_server_socket(
    exit_stack: asyncs.LABELS.exit_stack,
    params,
    ssl_context=None,
):
    return exit_stack.enter_context(
        servers.make_server_socket(
            (params.host.get(), params.port.get()),
            reuse_address=params.reuse_address.get(),
            reuse_port=params.reuse_port.get(),
            ssl_context=ssl_context,
        ),
    )
