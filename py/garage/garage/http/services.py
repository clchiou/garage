__all__ = [
    'ServiceError',
    'EndpointNotFound',
    'VersionNotSupported',
    'ServiceHub',
    'Service',
]

import logging
import re
from collections import namedtuple
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


class ServiceHub:

    def __init__(self):
        self.services = {}

    def add_service(self, service):
        LOG.info('register service %s version %d',
                 service.name, service.version)
        name = service.name.encode('ascii')
        services = self.services.setdefault(name, [])
        for i in range(len(services)):
            asserts.precond(service.version != services[i].version)
            if service.version < services[i].version:
                services.insert(i, service)
                break
        else:
            services.append(service)

    async def __call__(self, http_request, http_response):
        path = http_request.headers.get(b':path')
        if path is None:
            raise HttpError(HTTPStatus.BAD_REQUEST)
        service, endpoint = call_dispatch(self.dispatch, path)
        await service.call_endpoint(endpoint, http_request, http_response)

    PATTERN_SERVICE = re.compile(
        br'/([a-zA-Z0-9_\-.]+)/(\d+)/([a-zA-Z0-9_\-.]+)')

    def dispatch(self, path):
        match = self.PATTERN_SERVICE.fullmatch(path)
        if not match:
            raise EndpointNotFound(path)
        service_name = match.group(1)
        version = int(match.group(2))
        endpoint_name = match.group(3)

        services = self.services.get(service_name)
        if services is None:
            raise EndpointNotFound(path)

        for service in services:
            if service.version < version:
                continue
            endpoint = service.endpoints.get(endpoint_name)
            if endpoint is None:
                raise EndpointNotFound(path)
            LOG.info('dispatch %s to %s/%d/%s',
                     path.decode('ascii'),
                     service.name, service.version,
                     endpoint_name.decode('ascii'))
            return service, endpoint

        raise VersionNotSupported(version)


class Service:

    def __init__(self, name, version):
        LOG.info('create service %s version %d', name, version)
        self.name = name
        self.version = version
        self.policies = []
        self.endpoints = {}
        self.parse = None
        self.serialize = None

    def add_policies(self, policy):
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
        endpoint = call_dispatch(self.dispatch, path)
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


def call_dispatch(dispatch, path):
    try:
        return dispatch(path)
    except EndpointNotFound:
        raise HttpError(HTTPStatus.NOT_FOUND)
    except VersionNotSupported:
        raise HttpError(HTTPStatus.BAD_REQUEST)
