__all__ = [
    'DownloadError',
    'HttpError',
]


class DownloadError(Exception):
    pass


class HttpError(Exception):
    pass
