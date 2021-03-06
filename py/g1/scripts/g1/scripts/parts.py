from startup import startup

from g1.apps import bases
from g1.apps import parameters
from g1.bases import labels

from .. import scripts  # pylint: disable=relative-beyond-top-level

LABELS = labels.make_labels(
    'g1.scripts',
    'setup',
)

PARAMS = parameters.define(
    'g1.scripts',
    parameters.Namespace(
        dry_run=parameters.Parameter(False, 'whether to dry-run commands'),
    ),
)


@startup
def setup(
    exit_stack: bases.LABELS.exit_stack,
    _: parameters.LABELS.parameters,
) -> LABELS.setup:
    exit_stack.enter_context(scripts.doing_dry_run(PARAMS.dry_run.get()))
