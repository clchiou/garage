import logging

import foreman

from g1.operations.cores import models as ops_models

logging.getLogger(__name__).addHandler(logging.NullHandler())

# Name of the base image.
BASE = 'base'
# Label of the base image.
BASE_LABEL = foreman.Label.parse('//bases:%s' % BASE)

# Top-level directories.
RELEASE_ENVS_DIR_NAME = 'envs'
RELEASE_PODS_DIR_NAME = 'pods'
RELEASE_XARS_DIR_NAME = 'xars'
RELEASE_IMAGES_DIR_NAME = 'images'
RELEASE_VOLUMES_DIR_NAME = 'volumes'

# Pod directory structure.
POD_DIR_RELEASE_METADATA_FILENAME = 'release.json'
POD_DIR_DEPLOY_INSTRUCTION_FILENAME = \
    ops_models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME
POD_DIR_IMAGES_DIR_NAME = ops_models.POD_BUNDLE_IMAGES_DIR_NAME
POD_DIR_VOLUMES_DIR_NAME = ops_models.POD_BUNDLE_VOLUMES_DIR_NAME

# XAR directory structure.
XAR_DIR_RELEASE_METADATA_FILENAME = 'release.json'
XAR_DIR_DEPLOY_INSTRUCTION_FILENAME = \
    ops_models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME
XAR_DIR_IMAGE_FILENAME = ops_models.XAR_BUNDLE_IMAGE_FILENAME
XAR_DIR_ZIPAPP_FILENAME = ops_models.XAR_BUNDLE_ZIPAPP_FILENAME

# Image directory structure.
IMAGE_DIR_BUILDER_IMAGE_FILENAME = 'builder.tar.gz'
IMAGE_DIR_IMAGE_FILENAME = ops_models.POD_BUNDLE_IMAGE_FILENAME

# Volume directory structure.
VOLUME_DIR_VOLUME_FILENAME = ops_models.POD_BUNDLE_VOLUME_FILENAME


def is_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)
