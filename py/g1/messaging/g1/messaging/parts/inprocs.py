from g1.apps import asyncs
from g1.apps import utils
from g1.bases import labels

from ..reqrep import inprocs

SERVER_LABEL_NAMES = (
    # Input.
    'server',
)


def define_server(module_path=None):
    module_path = module_path or inprocs.__name__
    module_labels = labels.make_labels(module_path, *SERVER_LABEL_NAMES)
    setup_server(module_labels)
    return module_labels


def setup_server(module_labels):
    utils.define_maker(configure_server, {'server': module_labels.server})


def configure_server(exit_stack: asyncs.LABELS.exit_stack, server):
    exit_stack.enter_context(server)
