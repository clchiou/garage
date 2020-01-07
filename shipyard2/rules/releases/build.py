"""Set up the base environment for release processes."""

from pathlib import Path

import foreman

from g1.bases.assertions import ASSERT

(foreman.define_parameter.list_typed('sources')\
 .with_doc('host paths to source repositories')
 .with_default([Path(__file__).parent.parent.parent.parent]))

# Basically, this is the output directory in the host system.
(foreman.define_parameter.path_typed('root')\
 .with_doc('host path to the root directory of release repository'))

# Basically, this is the input directory in the host system.
(foreman.define_parameter.path_typed('shipyard-data')\
 .with_doc('host path to shipyard data directory (optional)'))


# NOTE: This rule is generally run in the host system, not inside a
# builder pod.
@foreman.rule
def build(parameters):
    ASSERT.all(parameters['sources'], _is_source_repo)
    ASSERT.predicate(parameters['root'], Path.is_dir)


def _is_source_repo(path):
    return (Path(path) / '.git').is_dir()
