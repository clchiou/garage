__all__ = [
    'ServiceError',
    'EndpointNotFound',
    'VersionNotSupported',
    'Service',
]

import asyncio
import logging
import re
from http import HTTPStatus

from http2 import HttpError

from garage import asserts
from garage.asyncs.futures import each_completed


LOG = logging.getLogger(__name__)


class ServiceError(Exception):
    pass


class EndpointNotFound(ServiceError):
    pass


class VersionNotSupported(ServiceError):
    pass


class Service:

    def __init__(self, name, version):
        LOG.info('create service %s version %d', name, version)
        self.name = name
        self.version = version
        self._root_path = None
        self.policies = []
        self.endpoints = {}
        self.decode = None
        self.encode = None

    @property
    def root_path(self):
        return self._root_path.decode('ascii')

    @root_path.setter
    def root_path(self, root_path):
        if isinstance(root_path, str):
            root_path = root_path.encode('ascii')
        self._root_path = root_path

    def add_policy(self, policy):
        self.policies.append(policy)

    def add_endpoint(self, name, endpoint):
        LOG.info('register endpoint %s to service %s version %d',
                 name, self.name, self.version)
        name = name.encode('ascii')
        asserts.precond(name not in self.endpoints)
        self.endpoints[name] = endpoint

    async def __call__(self, http_request, http_response):
        path = http_request.headers.get(b':path')
        if path is None:
            raise HttpError(HTTPStatus.BAD_REQUEST)

        try:
            endpoint = self.dispatch(path)
        except EndpointNotFound:
            raise HttpError(HTTPStatus.NOT_FOUND) from None
        except VersionNotSupported as e:
            # Returning 400 when a request's version is newer is weird,
            # but none of other 4xx or 5xx code makes more sense anyway.
            # Like, 403?  But, could we say we understand a request of
            # newer version (premise of a 403)?  At least when returning
            # 400, we are telling the client that he could modify the
            # request (down-version it) and send it again.
            raise HttpError(HTTPStatus.BAD_REQUEST) from None

        try:
            await self.call_endpoint(endpoint, http_request, http_response)
        except HttpError:
            raise
        except Exception:
            LOG.exception('err when calling endpoint')
            raise HttpError(HTTPStatus.INTERNAL_SERVER_ERROR)

    PATTERN_ENDPOINT = re.compile(br'/(\d+)/([\w_\-.]+)')

    def dispatch(self, path):
        if self._root_path:
            if not path.startswith(self._root_path):
                raise EndpointNotFound(path)
            path = path[len(self._root_path):]

        match = self.PATTERN_ENDPOINT.match(path)
        if not match:
            raise EndpointNotFound(path)
        version = int(match.group(1))
        endpoint_name = match.group(2)

        endpoint = self.endpoints.get(endpoint_name)
        if endpoint is None:
            raise EndpointNotFound(path)

        if self.version < version:
            raise VersionNotSupported(version)

        return endpoint

    async def call_endpoint(self, endpoint, http_request, http_response):
        # Run policies in parallel.
        policy_futs = [
            asyncio.ensure_future(policy(http_request.headers))
            for policy in self.policies
        ]
        try:
            async for fut in each_completed(policy_futs):
                await fut
        finally:
            for fut in policy_futs:
                fut.cancel()

        request = await http_request.body
        if request:
            if self.decode:
                request = self.decode(http_request.headers, request)
        else:
            request = None

        response = await endpoint(request)

        if self.encode:
            response = self.encode(http_request.headers, response)
        asserts.postcond(isinstance(response, bytes))

        http_response.headers[b':status'] = b'200'
        await http_response.write(response)
        http_response.close()
