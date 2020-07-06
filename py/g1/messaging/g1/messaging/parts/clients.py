import collections.abc

from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from ..reqrep import clients
from . import utils as parts_utils

CLIENT_LABEL_NAMES = (
    # Input.
    'client',
    # Private.
    'client_params',
)


def define_client(module_path=None, **kwargs):
    module_path = module_path or clients.__name__
    module_labels = labels.make_labels(module_path, *CLIENT_LABEL_NAMES)
    setup_client(
        module_labels,
        parameters.define(module_path, make_client_params(**kwargs)),
    )
    return module_labels


def setup_client(module_labels, module_params):
    utils.depend_parameter_for(module_labels.client_params, module_params)
    utils.define_maker(
        configure_client,
        {
            'client': module_labels.client,
            'params': module_labels.client_params,
        },
    )


def make_client_params(
    *,
    urls=None,
    validate_urls=bool,  # Merely check non-empty for now.
    send_timeout=2,
    recv_timeout=4,
):
    return parameters.Namespace(
        'configure messaging client',
        urls=parameters.make_parameter(
            urls,
            collections.abc.Iterable,
            'urls that client connects to',
            validate=validate_urls,
        ),
        send_timeout=parameters.Parameter(
            send_timeout,
            type=(type(None), int, float),
            unit='seconds',
        ),
        recv_timeout=parameters.Parameter(
            recv_timeout,
            type=(type(None), int, float),
            unit='seconds',
        ),
    )


def configure_client(
    exit_stack: asyncs.LABELS.exit_stack,
    client,
    params,
):
    exit_stack.enter_context(client)
    if params.send_timeout.get() is not None:
        client.socket.send_timeout = parts_utils.to_milliseconds_int(
            params.send_timeout.get()
        )
    if params.recv_timeout.get() is not None:
        client.socket.recv_timeout = parts_utils.to_milliseconds_int(
            params.recv_timeout.get()
        )
    for url in params.urls.get():
        client.socket.dial(url)
