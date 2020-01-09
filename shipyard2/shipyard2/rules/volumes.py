"""Helpers for writing rules under //volumes."""

__all__ = [
    'get_volume_path',
]

import foreman

import shipyard2


# NOTE: This function is generally called in the host system, not inside
# a builder pod.
def get_volume_path(parameters, label, version):
    # We require absolute label for now.
    label = foreman.Label.parse(label)
    return (
        parameters['//releases:root'] / \
        shipyard2.RELEASE_VOLUMES_DIR_NAME /
        label.path /
        label.name /
        version /
        shipyard2.VOLUME_DIR_VOLUME_FILENAME
    )
