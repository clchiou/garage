"""Set up the base environment for pod release processes."""

import foreman

# `build` is a do-nothing rule at the moment.
foreman.define_rule('build').depend('//releases:build')
