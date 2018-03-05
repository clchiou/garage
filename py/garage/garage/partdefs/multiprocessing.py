from garage import multiprocessing
from garage import parameters
from garage import parts
from garage.partdefs import apps


PARTS = parts.PartList(multiprocessing.__name__, [
    ('python2', parts.AUTO),
])


PARAMS = parameters.define_namespace(
    multiprocessing.__name__, 'execute legacy Python 2 code')
PARAMS.python2 = parameters.create(
    'python2', 'set path to or command of python2 executable')
PARAMS.python2_max_workers = parameters.create(
    8, 'set max concurrent python2 worker threads')


@parts.define_maker
def make_python2(exit_stack: apps.PARTS.exit_stack) -> PARTS.python2:
    return exit_stack.enter_context(multiprocessing.python(
        executable=PARAMS.python2.get(),
        max_workers=PARAMS.python2_max_workers.get(),
    ))
