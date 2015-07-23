__all__ = [
    'ForwardingHttpClient',
]


class ForwardingHttpClient:

    def __init__(self, client):
        self.__client = client

    def get(self, uri, **kwargs):
        uri, kwargs = self.on_request(uri, kwargs)
        return self.on_response(self.__client.get(uri, **kwargs))

    def post(self, uri, **kwargs):
        uri, kwargs = self.on_request(uri, kwargs)
        return self.on_response(self.__client.post(uri, **kwargs))

    def head(self, uri, **kwargs):
        uri, kwargs = self.on_request(uri, kwargs)
        return self.on_response(self.__client.head(uri, **kwargs))

    def on_request(self, uri, kwargs):
        """Hook for modifying URI and kwargs."""
        return uri, kwargs

    def on_response(self, response):
        """Hook for modifying response object."""
        return response
