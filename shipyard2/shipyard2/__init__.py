import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

BASE = 'base'

# Top-level directories.
RELEASE_ENVS_DIR_NAME = 'envs'
RELEASE_PODS_DIR_NAME = 'pods'
RELEASE_IMAGES_DIR_NAME = 'images'
RELEASE_VOLUMES_DIR_NAME = 'volumes'

# Pod directory structure.
POD_DIR_RELEASE_METADATA_FILENAME = 'release.json'
POD_DIR_DEPLOY_INSTRUCTION_FILENAME = 'deploy.json'
POD_DIR_IMAGES_DIR_NAME = 'images'
POD_DIR_VOLUMES_DIR_NAME = 'volumes'

# Image directory structure.
IMAGE_DIR_BUILDER_IMAGE_FILENAME = 'builder.tar.gz'
IMAGE_DIR_IMAGE_FILENAME = 'image.tar.gz'

# Volume directory structure.
VOLUME_DIR_VOLUME_FILENAME = 'volume.tar.gz'


def is_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)
