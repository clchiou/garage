__all__ = [
    'V8Component',
]

from garage import components
from garage.threads.utils import make_get_thread_local

from v8 import V8


class V8Component(components.Component):

    require = components.EXIT_STACK

    provide = components.make_fqname_tuple(__name__, 'get_v8_isolate')

    def make(self, require):
        exit_stack = require.exit_stack
        v8 = exit_stack.enter_context(V8())
        return make_get_thread_local(
            'v8_isolate',
            lambda: exit_stack.enter_context(v8.isolate()),
        )
