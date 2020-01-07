"""Set up the base environment for pod release processes."""

import foreman

from g1.bases.assertions import ASSERT

# For now, (we artificially restrict that) you can only build one pod at
# a time.  That is why we have only one pod version parameter here.
(foreman.define_parameter('version')\
 .with_doc('pod version'))


@foreman.rule
@foreman.rule.depend('//releases:build')
def build(parameters):
    ASSERT.not_none(parameters['version'])
