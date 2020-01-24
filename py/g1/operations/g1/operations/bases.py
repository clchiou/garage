__all__ = [
    'get_zipapp_target_path',
]

from g1.apps import parameters

PARAMS = parameters.define(
    'g1.operations',
    parameters.Namespace(
        zipapp_directory=parameters.Parameter(
            '/usr/local/bin',
            doc='path to install zipapp',
            type=str,
        ),
    ),
)


def get_zipapp_target_path(name):
    return Path(PARAMS.zipapp_directory.get()) / name
