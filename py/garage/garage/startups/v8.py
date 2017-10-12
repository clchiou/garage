__all__ = [
    'V8Component',
]

from garage import components

from v8 import V8


class V8Component(components.Component):

    require = components.EXIT_STACK

    provide = components.make_fqname_tuple(__name__, 'v8')

    def make(self, require):
        return require.exit_stack.enter_context(V8())
