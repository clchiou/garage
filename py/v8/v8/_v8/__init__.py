"""Low-level interface to V8."""

__all__ = [
    'V8',
]

import logging
import os.path

from garage import asserts

from .base import C, ObjectBase
from .utils import not_null


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
        return Context(self.isolate)

    def handle_scope(self):
        return HandleScope(self.isolate)


class Context(ObjectBase):

    _spec = ObjectBase.Spec(
        name='context',
        ctor=C.v8_context_new,
        dtor=C.v8_context_delete,
        enter=C.v8_context_enter,
        exit=C.v8_context_exit,
    )


class HandleScope(ObjectBase):

    _spec = ObjectBase.Spec(
        name='handle_scope',
        ctor=C.v8_handle_scope_new,
        dtor=C.v8_handle_scope_delete,
    )
