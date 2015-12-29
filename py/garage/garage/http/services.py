__all__ = [
    'ServiceError',
    'EndpointNotFound',
    'VersionNotSupported',
    'Service',
    'Version',
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

    def __init__(self, version):
        self._path = b'/'
        self.version = version
        self.policies = []
        self.endpoints = {}
        self.parse = None
        self.serialize = None

    @property
    def path(self):
        return self._path.decode('ascii')

    @path.setter
    def path(self, new_path):
        self._path = new_path.encode('ascii')
        if self._path[-1] != b'/':
            self._path += b'/'

    def add_policies(self, policy):
        self.policies.append(policy)

    def add_endpoint(self, name, endpoint):
        name = name.encode('ascii')
        asserts.precond(name not in self.endpoints)
        self.endpoints[name] = endpoint

    async def __call__(self, http_request, http_response):
        try:
            endpoint = self.dispatch(http_request)
            await self.call_endpoint(endpoint, http_request, http_response)
        except EndpointNotFound:
            raise HttpError(HTTPStatus.NOT_FOUND)
        except VersionNotSupported:
            raise HttpError(HTTPStatus.BAD_REQUEST)

    def dispatch(self, http_request):
        path = http_request.headers.get(b':path')
        if path is None:
            raise EndpointNotFound(None)
        version, name = parse_path(self._path, path)
        if version is None:
            raise EndpointNotFound(path)
        endpoint = self.endpoints.get(name)
        if endpoint is None:
            raise EndpointNotFound(path)
        if not self.version.is_compatible_with(version):
            raise VersionNotSupported(version)
        return endpoint

    async def call_endpoint(self, endpoint, http_request, http_response):
        for policy in self.policies:
            await policy(http_request.headers)

        request = await http_request.body
        if self.parse:
            request = await self.parse(http_request.headers, request)

        response = await endpoint(request)
        if self.serialize:
            response = await self.serialize(http_request.headers, response)

        http_response.headers[b':status'] = b'200'
        await http_response.write(response)
        await http_response.close()


def parse_path(root, path):
    if not path.startswith(root):
        return None, None
    i = path.find(b'/', len(root))
    if i == -1:
        return None, None
    try:
        version = Version.parse(path[len(root):i])
    except ValueError:
        return None, None
    j = path.find(b'?', i)
    if j == -1:
        j = path.find(b'#', i)
    if j == -1:
        name = path[i+1:]
    else:
        name = path[i+1:j]
    return version, name


class Version(namedtuple('Version', 'major minor patch')):

    # Should I forbid leading zeros?
    PATTERN_VERSION = re.compile(br'(\d+)\.(\d+)\.(\d+)')

    @classmethod
    def parse(cls, version):
        match = cls.PATTERN_VERSION.fullmatch(version)
        if not match:
            raise ValueError(version)
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    def __str__(self):
        return '%d.%d.%d' % self

    def is_compatible_with(self, other):
        return self.major == other.major
