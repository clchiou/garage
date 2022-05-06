"""Cluster session.

The go-to session type is quite versatile, and should be able to handle
most complex use cases, such as:

* If you want different rate limit or retry configuration for each kind
  of request, you could create ordinary sessions with a common executor.

* If you want to prioritize requests, pass a priority executor to an
  ordinary session.

The cluster session is mostly for just one specific use case: If you
want multiple kinds of priority, and there is no easy way to compare
different kinds of priority.  With a cluster session, requests are first
prioritized within its own kind, and then requests from each kind are
sent in a round-robin order.
"""

__all__ = [
    'ClusterSession',
    'ClusterStub',
]

import dataclasses
import typing

from g1.asyncs.bases import futures
from g1.asyncs.bases import more_queues
from g1.asyncs.bases import queues
from g1.asyncs.bases import tasks
from g1.bases.assertions import ASSERT

from . import bases


class ClusterSession:
    """Cluster session.

    This multiplexes request queues of cluster stubs.
    """

    def __init__(
        self,
        cluster_stubs,
        executor=None,
        num_pools=0,
        num_connections_per_pool=0,
    ):
        ASSERT.not_empty(cluster_stubs)
        self._base_session = bases.BaseSession(
            executor=executor,
            num_pools=num_pools,
            num_connections_per_pool=num_connections_per_pool,
        )
        self._cluster_stubs = cluster_stubs
        for cluster_stub in self._cluster_stubs:
            ASSERT.none(cluster_stub._base_session)
            cluster_stub._base_session = self._base_session

    async def serve(self):
        async for tagged_item in more_queues.select(
            cluster_stub._queue for cluster_stub in self._cluster_stubs
        ):
            request, kwargs, future = tagged_item.item
            future.set_result(
                tasks.spawn(self._base_session.send(request, **kwargs))
            )

    def shutdown(self):
        for cluster_stub in self._cluster_stubs:
            cluster_stub._queue.close()

    @property
    def headers(self):
        return self._base_session.headers

    @property
    def cookies(self):
        return self._base_session.cookies

    def update_cookies(self, cookie_dict):
        return self._base_session.update_cookies(cookie_dict)

    async def send(self, request, **kwargs):
        return await self._base_session.send(request, **kwargs)

    def send_blocking(self, request, **kwargs):
        return self._base_session.send_blocking(request, **kwargs)


class ClusterStub:
    """Cluster stub.

    All cluster stub share one cluster session.  Each cluster stub has
    its own request queue.

    NOTE: Each stub has its own local cache.  If this turns out to be
    undesirable, we could move the local cache to the cluster session.

    NOTE: On the other hand, all stubs share the cluster session's
    headers and cookies.  If this turns out to be undesirable, we could
    set up "virtual" headers and cookies in each stub.
    """

    def __init__(self, *, queue=None, **kwargs):
        # Only support priority queue use case for now.  For other use
        # cases, the ordinary go-to session type should be sufficient.
        if queue is not None:
            ASSERT.isinstance(queue, queues.PriorityQueue)
        else:
            queue = queues.PriorityQueue()
        self._queue = queue
        self._sender = bases.Sender(self._send, **kwargs)
        self._base_session = None  # Set by ClusterSession.

    def _get_base_session(self):
        return ASSERT.not_none(self._base_session)

    async def _send(self, request, *, priority, **kwargs):
        future = futures.Future()
        await self._queue.put(
            TaggedItem(priority=priority, item=(request, kwargs, future))
        )
        return await (await future.get_result()).get_result()

    @property
    def headers(self):
        return self._get_base_session().headers

    @property
    def cookies(self):
        return self._get_base_session().cookies

    def update_cookies(self, cookie_dict):
        return self._get_base_session().update_cookies(cookie_dict)

    # Make priority a required argument.
    async def send(self, request, *, priority, **kwargs):
        return await self._sender(request, priority=priority, **kwargs)

    def send_blocking(self, request, **kwargs):
        return self._get_base_session().send_blocking(request, **kwargs)


@dataclasses.dataclass(frozen=True, order=True)
class TaggedItem:
    priority: typing.Any
    item: typing.Any = dataclasses.field(compare=False)
