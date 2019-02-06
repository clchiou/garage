"""Demonstrate ``g1.apps.parameters``."""

from startup import startup

from g1.apps import bases
from g1.apps import labels
from g1.apps import parameters
from g1.apps import utils

LABELS = labels.make_labels(
    __name__,
    'f',
    'x',
)

PARAMS = parameters.define(
    __name__,
    parameters.Namespace(x=parameters.Parameter(0)),
)

utils.depend_parameter_for(LABELS.x, PARAMS.x)


def square(x):
    return x * x


@startup
def bind(x: LABELS.x) -> LABELS.f:
    x = x.get()
    return lambda: square(x)


def main(f: LABELS.f):
    print('f() = %d' % f())
    return 0


if __name__ == '__main__':
    bases.run(main)
