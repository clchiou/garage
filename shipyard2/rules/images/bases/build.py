"""Set up the base environment for image release processes."""

from pathlib import Path

import foreman

from g1.bases.assertions import ASSERT

import shipyard2
import shipyard2.rules.images

#
# Although container runtime accepts multiple images, for simplicity we
# will only produce one application image per pod.  That is why we only
# have one image version parameter.
#

SHIPYARD2_PATH = Path(__file__).parent.parent.parent.parent

(foreman.define_parameter.path_typed('builder')\
 .with_doc('host path to script builder.sh')
 .with_default(SHIPYARD2_PATH / 'scripts' / 'builder.sh'))

(foreman.define_parameter.path_typed('ctr')\
 .with_doc('host path to script ctr.sh')
 .with_default(SHIPYARD2_PATH / 'scripts' / 'ctr.sh'))

(foreman.define_parameter('builder-id')\
 .with_doc('builder pod id (optional)'))

(foreman.define_parameter('base-version')\
 .with_doc('base image version'))

(foreman.define_parameter.list_typed('builder-images')\
 .with_doc(
     'list of intermediate builder images where each image is either: '
     '"id:XXX", "nv:XXX:YYY", or "tag:XXX"')
 .with_default([]))

(foreman.define_parameter.list_typed('filters')\
 .with_doc(
     'list of filter rules where each rule is either: '
     '"include:XXX", or "exclude:XXX"')
 .with_default([]))

(foreman.define_parameter('version')\
 .with_doc('application image version'))


# NOTE: This rule is generally run in the host system, not inside a
# builder pod.
@foreman.rule
@foreman.rule.depend('//releases:build')
def build(parameters):
    ASSERT.predicate(SHIPYARD2_PATH.parent / '.git', Path.is_dir)
    ASSERT.predicate(parameters['//images/bases:builder'], Path.is_file)
    ASSERT.predicate(parameters['//images/bases:ctr'], Path.is_file)
    base_version = ASSERT.not_none(parameters['base-version'])
    ASSERT.not_none(parameters['version'])
    # We do not build but merely check the presence for base and
    # builder-base image in the release directory (we assume that they
    # have been built through some other means).
    for base_name in (shipyard2.BASE, shipyard2.BUILDER_BASE):
        ASSERT.predicate(
            shipyard2.rules.images.get_image_path(
                parameters, base_name, base_version
            ),
            Path.is_file,
        )


@foreman.rule
@foreman.rule.depend('//releases:build')
@foreman.rule.depend('build')
def bootstrap(parameters):
    shipyard2.rules.images.bootstrap(parameters)
