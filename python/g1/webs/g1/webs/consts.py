"""HTTP constants."""

__all__ = [
    'UrlPath',
    # Request methods.
    'METHOD_CONNECT',
    'METHOD_DELETE',
    'METHOD_GET',
    'METHOD_HEAD',
    'METHOD_OPTIONS',
    'METHOD_POST',
    'METHOD_PUT',
    'METHOD_TRACE',
    # Response statuses.
    'Statuses',
    # Response headers.
    'HEADER_ACCEPT_LANGUAGE',
    'HEADER_ALLOW',
    'HEADER_CONTENT_LANGUAGE',
    'HEADER_CONTENT_LENGTH',
    'HEADER_CONTENT_TYPE',
    'HEADER_DATE',
    'HEADER_ETAG',
    'HEADER_IF_NONE_MATCH',
    'HEADER_LOCATION',
    'HEADER_RETRY_AFTER',
]

# Rename HTTPStatus for consistency.
from http import HTTPStatus as Statuses
from pathlib import PurePosixPath as UrlPath

METHOD_CONNECT = 'CONNECT'
METHOD_DELETE = 'DELETE'
METHOD_GET = 'GET'
METHOD_HEAD = 'HEAD'
METHOD_OPTIONS = 'OPTIONS'
METHOD_POST = 'POST'
METHOD_PUT = 'PUT'
METHOD_TRACE = 'TRACE'

HEADER_ACCEPT_LANGUAGE = 'Accept-Language'
HEADER_ALLOW = 'Allow'
HEADER_CONTENT_LANGUAGE = 'Content-Language'
HEADER_CONTENT_LENGTH = 'Content-Length'
HEADER_CONTENT_TYPE = 'Content-Type'
HEADER_DATE = 'Date'
HEADER_ETAG = 'ETag'
HEADER_IF_NONE_MATCH = 'If-None-Match'
HEADER_LOCATION = 'Location'
HEADER_RETRY_AFTER = 'Retry-After'
