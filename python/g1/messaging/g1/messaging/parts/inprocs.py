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
    del module_labels  # Unused.
