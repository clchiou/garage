__all__ = [
    'V8',
]

import logging
import os.path
from collections import OrderedDict
from contextlib import ExitStack

from garage import asserts

from .base import C, ObjectBase
from .utils import (
    from_js,
    make_scoped,
    not_null,
)
from .values import (
    Object,
    ObjectDictProxy,
    Script,
    String,
)


LOG = logging.getLogger(__name__)


class V8:

    def __init__(self, natives_blob_path, snapshot_blob_path):
        asserts.precond(os.path.exists(natives_blob_path))
        asserts.precond(os.path.exists(snapshot_blob_path))
        LOG.info('initialize V8')
        asserts.postcond(C.v8_initialize_icu(None))
        C.v8_initialize_external_startup_data2(
            natives_blob_path.encode('utf-8'),
            snapshot_blob_path.encode('utf-8'),
        )
        self.platform = not_null(C.v8_platform_create_default_platform(0))
        try:
            C.v8_initialize_platform(self.platform)
            asserts.postcond(C.v8_initialize())
        except Exception:
            C.v8_platform_delete(self.platform)
            raise

    def close(self):
        asserts.precond(self.platform is not None)
        LOG.info('tear down V8')
        asserts.postcond(C.v8_dispose())
        C.v8_shutdown_platform()
        C.v8_platform_delete(self.platform)
        self.platform = None

    def isolate(self):
        asserts.precond(self.platform is not None)
        params = not_null(C.v8_isolate_create_params_new())
        try:
            return Isolate(params)
        finally:
            C.v8_isolate_create_params_delete(params)


class Isolate(ObjectBase):

    _spec = ObjectBase.Spec(
        name='isolate',
        ctor=C.v8_isolate_new,
        dtor=C.v8_isolate_dispose,
        enter=C.v8_isolate_enter,
        exit=C.v8_isolate_exit,
        level=logging.INFO,
    )

    isolate = None

    def context(self):
        return Context(self)

    def handle_scope(self):
        return HandleScope(not_null(self.isolate))

    def string(self, string):
        return String(not_null(self.isolate), string.encode('utf-8'))


class Context(ObjectBase):

    _spec = ObjectBase.Spec(
        name='context',
        extra=['isolate'],
        ctor=(lambda isolate:
              (C.v8_context_new(not_null(isolate.isolate)), isolate)),
        dtor=C.v8_context_delete,
        enter=C.v8_context_enter,
        exit=C.v8_context_exit,
    )

    context = None
    isolate = None

    def execute(self, source):
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            source = scoped(self.isolate.string(source))
            script = scoped(Script.compile(self, source))
            scoped(script.run(self))

    def vars(self):
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            varz = ObjectDictProxy(
                self,
                scoped(Object(C.v8_context_global(not_null(self.context)))),
            )
            return OrderedDict(
                (from_js(name), from_js(scoped(varz[name])))
                for name in map(scoped, varz)
            )


class HandleScope(ObjectBase):

    _spec = ObjectBase.Spec(
        name='handle_scope',
        ctor=C.v8_handle_scope_new,
        dtor=C.v8_handle_scope_delete,
    )
