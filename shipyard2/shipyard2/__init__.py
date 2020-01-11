import logging
from pathlib import Path

import foreman

from g1.bases.assertions import ASSERT

logging.getLogger(__name__).addHandler(logging.NullHandler())

REPO_ROOT_PATH = Path(__file__).parent.parent.parent

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


def make_help_kwargs(help_text):
    return {
        'help': help_text,
        'description': '%s%s.' % (help_text[0].upper(), help_text[1:]),
    }


def is_source_repo(path):
    return (path / '.git').is_dir()


def get_builder_path():
    return ASSERT.predicate(
        REPO_ROOT_PATH / 'shipyard2' / 'scripts' / 'builder.sh',
        Path.is_file,
    )


def get_ctr_path():
    return ASSERT.predicate(
        REPO_ROOT_PATH / 'shipyard2' / 'scripts' / 'ctr.sh',
        Path.is_file,
    )


def get_foreman_path():
    return ASSERT.predicate(
        REPO_ROOT_PATH / 'shipyard2' / 'scripts' / 'foreman.sh',
        Path.is_file,
    )


ASSERT.predicate(REPO_ROOT_PATH, is_source_repo)


def look_like_image_rule(rule):
    return rule.path.parts[0] == RELEASE_IMAGES_DIR_NAME


def look_like_pod_rule(rule):
    return rule.path.parts[0] == RELEASE_PODS_DIR_NAME


def guess_label_from_rule(rule):
    """Guess pod or image label from build rule.

    For example, //pod/foo:bar/build becomes //foo:bar.
    """
    name_parts = rule.name.parts
    ASSERT(
        len(name_parts) == 2 and name_parts[1] == 'build',
        'expect pod or image build rule: {}',
        rule,
    )
    return foreman.Label.parse(
        '//%s:%s' % ('/'.join(rule.path.parts[1:]), name_parts[0])
    )


def get_builder_name(name):
    return name + '-builder'
