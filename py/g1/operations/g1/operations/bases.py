__all__ = [
    'get_zipapp_target_path',
]

from pathlib import Path

from g1.apps import parameters

PARAMS = parameters.define(
    'g1.operations',
    parameters.Namespace(
        zipapp_directory=parameters.Parameter(
            Path('/usr/local/bin'),
            doc='path to install zipapp',
            type=Path,
            parse=Path,
            validate=Path.is_absolute,
            format=str,
        ),
    ),
)


def get_zipapp_target_path(name):
    return PARAMS.zipapp_directory.get() / name
