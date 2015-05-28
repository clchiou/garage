__all__ = [
    'DownloadError',
    'HttpError',
    'get_status_code',
]


class DownloadError(Exception):
    pass


class HttpError(Exception):
    pass


def get_status_code(exc):
    if exc.response is not None:
        status_code = exc.response.status_code
    else:
        status_code = -1
    return status_code
