"""Helpers for writing rules under //volumes."""

__all__ = [
    'get_volume_path',
]

import foreman

_VOLUME_FILENAME = 'volume.tar.gz'


# NOTE: This function is generally called in the host system, not inside
# a builder pod.
def get_volume_path(parameters, label, version):
    # We require absolute label for now.
    label = foreman.Label.parse(label)
    return (
        parameters['//releases:root'] / \
        'volumes' /
        label.path /
        label.name /
        version /
        _VOLUME_FILENAME
    )
