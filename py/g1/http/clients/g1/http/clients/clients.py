__all__ = [
    'Session',
]

from . import bases


class Session:
    """Session.

    For most use cases, this is your go-to choice.  It supports local
    cache, rate limit, retry, and priority (when given a priority
    executor).
    """

    def __init__(
        self,
        *,
        executor=None,
        num_pools=0,
        num_connections_per_pool=0,
        **kwargs,
    ):
        self._base_session = bases.BaseSession(
            executor=executor,
            num_pools=num_pools,
            num_connections_per_pool=num_connections_per_pool,
        )
        self._sender = bases.Sender(self._base_session.send, **kwargs)

    @property
    def headers(self):
        return self._base_session.headers

    @property
    def cookies(self):
        return self._base_session.cookies

    def update_cookies(self, cookie_dict):
        return self._base_session.update_cookies(cookie_dict)

    async def send(self, request, **kwargs):
        return await self._sender(request, **kwargs)

    def send_blocking(self, request, **kwargs):
        return self._base_session.send_blocking(request, **kwargs)
