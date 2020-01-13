"""Set up the base environment for release processes."""

from pathlib import Path

import foreman

from g1.bases.assertions import ASSERT

# Basically, this is the output directory in the host system.
(foreman.define_parameter.path_typed('root')\
 .with_doc('host path to the root directory of release repository'))

# Basically, this is the input directory in the host system.
(foreman.define_parameter.path_typed('shipyard-data')\
 .with_doc('host path to shipyard data directory (optional)'))


# Add //bases:dummy to import //bases:roots parameter.
@foreman.rule
@foreman.rule.depend('//bases:dummy')
def build(parameters):
    ASSERT.predicate(parameters['root'], Path.is_dir)
