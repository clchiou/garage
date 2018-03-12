from garage import parts
from garage.partdefs import apps

import v8


PARTS = parts.Parts(v8.__name__)
PARTS.v8 = parts.AUTO


@parts.define_maker
def make_v8(exit_stack: apps.PARTS.exit_stack) -> PARTS.v8:
    return exit_stack.enter_context(v8.V8())
