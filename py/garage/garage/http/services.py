__all__ = [
    'ServiceError',
    'EndpointNotFound',
    'VersionNotSupported',
    'Service',
]

import re
from collections import namedtuple
from http import HTTPStatus

from http2 import HttpError

from garage import asserts


class ServiceError(Exception):
    pass


class EndpointNotFound(ServiceError):
    pass


class VersionNotSupported(ServiceError):
    pass


class Service:

    def __init__(self, name, version):
        self.name = name
        self.version = version
        self.policies = []
        self.endpoints = {}
        self.parse = None
        self.serialize = None

    def add_policies(self, policy):
        self.policies.append(policy)

    def add_endpoint(self, name, endpoint):
        name = name.encode('ascii')
        asserts.precond(name not in self.endpoints)
        self.endpoints[name] = endpoint

    async def __call__(self, http_request, http_response):
        try:
            endpoint = self.dispatch(http_request)
        except EndpointNotFound:
            raise HttpError(HTTPStatus.NOT_FOUND)
        except VersionNotSupported:
            raise HttpError(HTTPStatus.BAD_REQUEST)
        await self.call_endpoint(endpoint, http_request, http_response)

    def dispatch(self, http_request):
        path = http_request.headers.get(b':path')
        if path is None:
            raise EndpointNotFound(None)
        try:
            version, name = parse_path(path)
        except ValueError:
            raise EndpointNotFound(path)
        endpoint = self.endpoints.get(name)
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


PATTERN_PATH = re.compile(br'/(\d+)/([a-zA-Z0-9_\-.]+)')


def parse_path(path):
    match = PATTERN_PATH.match(path)
    if not match:
        raise ValueError(path)
    version = int(match.group(1))
    endpoint = match.group(2)
    return version, endpoint
