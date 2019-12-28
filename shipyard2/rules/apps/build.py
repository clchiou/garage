"""Base of application image."""

from pathlib import Path

import foreman

from g1.bases.assertions import ASSERT

(foreman.define_parameter.path_typed('root')\
 .with_doc('path to the root directory of this repository')
 .with_default(Path(__file__).parent.parent.parent.parent))

(foreman.define_parameter.path_typed('drydock')\
 .with_doc('path to the directory of intermediate build artifacts')
 .with_default(Path.home() / 'drydock'))


@foreman.rule
def build(parameters):
    ASSERT.predicate(parameters['root'] / '.git', Path.is_dir)
    parameters['drydock'].mkdir(exist_ok=True)
