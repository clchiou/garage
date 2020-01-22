import logging

import foreman

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
POD_DIR_DEPLOY_INSTRUCTION_FILENAME = 'deploy.json'
POD_DIR_IMAGES_DIR_NAME = 'images'
POD_DIR_VOLUMES_DIR_NAME = 'volumes'

# XAR directory structure.
XAR_DIR_RELEASE_METADATA_FILENAME = 'release.json'
XAR_DIR_DEPLOY_INSTRUCTION_FILENAME = 'deploy.json'
XAR_DIR_IMAGE_FILENAME = 'image.tar.gz'
XAR_DIR_ZIPAPP_FILENAME = 'app.zip'

# Image directory structure.
IMAGE_DIR_BUILDER_IMAGE_FILENAME = 'builder.tar.gz'
IMAGE_DIR_IMAGE_FILENAME = 'image.tar.gz'

# Volume directory structure.
VOLUME_DIR_VOLUME_FILENAME = 'volume.tar.gz'


def is_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)
