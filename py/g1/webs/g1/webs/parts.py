from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

import g1.http.servers.parts

from . import wsgi_apps

WEB_APP_LABEL_NAMES = (
    'handler',
    ('server', g1.http.servers.parts.HTTP_SERVER_LABEL_NAMES),
)


def define_web_app(module_path=None, **kwargs):
    module_path = module_path or __package__
    module_labels = labels.make_nested_labels(module_path, WEB_APP_LABEL_NAMES)
    setup_web_app(
        module_labels,
        parameters.define(module_path, make_web_app_params(**kwargs)),
    )
    return module_labels


def setup_web_app(module_labels, module_params):
    utils.define_maker(
        make_web_app,
        {
            'handler':
            module_labels.handler,
            'return': (
                module_labels.server.application,
                g1.asyncs.servers.parts.LABELS.serve,
                g1.asyncs.servers.parts.LABELS.shutdown,
            ),
        },
    )
    g1.http.servers.parts.setup_http_server(
        module_labels.server,
        module_params.server,
    )


def make_web_app_params(**kwargs):
    return parameters.Namespace(
        server=g1.http.servers.parts.make_server_socket_params(**kwargs),
    )


def make_web_app(handler):
    web_app = wsgi_apps.Application(handler)
    return web_app, web_app.serve, web_app.shutdown
