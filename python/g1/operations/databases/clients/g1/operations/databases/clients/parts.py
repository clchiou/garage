import g1.messaging.parts.clients
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels
# For now these are just aliases.
from g1.messaging.parts.clients import CLIENT_LABEL_NAMES
from g1.messaging.parts.clients import make_client_params

from .. import clients  # pylint: disable=relative-beyond-top-level


def define_client(module_path=None, **kwargs):
    module_path = module_path or clients.__name__
    module_labels = labels.make_labels(module_path, *CLIENT_LABEL_NAMES)
    setup_client(
        module_labels,
        parameters.define(module_path, make_client_params(**kwargs)),
    )
    return module_labels


def setup_client(module_labels, module_params):
    utils.define_maker(clients.make_client, {'return': module_labels.client})
    g1.messaging.parts.clients.setup_client(module_labels, module_params)
