__all__ = [
    'ServiceError',
    'EndpointNotFound',
    'VersionNotSupported',
    'Service',
]

import logging
import re
from http import HTTPStatus

from http2 import HttpError

from garage import asserts


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
        self.policies = []
        self.endpoints = {}
        self.parse = None
        self.serialize = None

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
            raise HttpError(HTTPStatus.NOT_FOUND)
        except VersionNotSupported:
            raise HttpError(HTTPStatus.BAD_REQUEST)
        await self.call_endpoint(endpoint, http_request, http_response)

    PATTERN_ENDPOINT = re.compile(br'/(\d+)/([a-zA-Z0-9_\-.]+)')

    def dispatch(self, path):
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
        for policy in self.policies:
            await policy(http_request.headers)

        request = await http_request.body
        if request:
            if self.parse:
                request = await self.parse(http_request.headers, request)
        else:
            request = None

        response = await endpoint(request)
        if self.serialize:
            response = await self.serialize(http_request.headers, response)
        asserts.postcond(isinstance(response, bytes))

        http_response.headers[b':status'] = b'200'
        await http_response.write(response)
        await http_response.close()
