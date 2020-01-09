"""Set up the base environment for image release processes."""

import foreman

from g1.bases.assertions import ASSERT

import shipyard2.rules.images

#
# Although container runtime accepts multiple images, for simplicity we
# will only produce one application image per pod.  That is why we only
# have one image version parameter.
#

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
    ASSERT.not_none(parameters['base-version'])
    ASSERT.not_none(parameters['version'])


@foreman.rule
@foreman.rule.depend('//releases:build')
@foreman.rule.depend('build')
def bootstrap(parameters):
    shipyard2.rules.images.bootstrap(parameters)
