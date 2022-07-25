"""Parser utilities."""

__all__ = [
    'ContextualParser',
]

import html
import urllib.parse
from pathlib import PurePosixPath

from g1.bases import assertions
from g1.bases import classes


class ContextualParser:
    """Contextual parser.

    You are expected to sub-class this class to add additional parse
    functions.  Although it seems like abusing class inheritance, as
    parse functions are almost exclusively pure functions, it provides a
    few benefits over pure functions:

    * Improve error reporting: You may simply use ``self.assert_``, and
      the request contents is appended to the error message; parse
      functions will no longer take an extra ``request`` argument only
      for generating contextual error messages.

    * Hide intermediate results among parse functions from your callers.
      Since most of intermediate results are private to your parse
      functions, they should not be exposed to your callers.  Also, this
      reduces burden on your parse function callers, as they do not have
      to carry around these intermediate results just for passing them
      to parse functions.
    """

    # You may override this type in sub-classes.
    ERROR_TYPE = AssertionError

    def __init__(self, request, response):
        self.request = request
        self.response = response
        self.assert_ = assertions.Assertions(self.__make_exc)

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['assert_']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.assert_ = assertions.Assertions(self.__make_exc)

    def __make_exc(self, message, *_):
        return self.ERROR_TYPE('%s, request=%r' % (message, self.request))

    @classes.memorizing_property
    def document(self):
        return self.response.html()

    @classes.memorizing_property
    def parsed_url(self):
        return urllib.parse.urlparse(self.request.url)

    @classes.memorizing_property
    def query(self):
        # pylint: disable=no-member
        return self.query_as_dict(self.parsed_url.query)

    def absolute_url(self, maybe_relative_url):
        """Return an absolute URL."""
        return urllib.parse.urljoin(self.request.url, maybe_relative_url)

    def split_url_path(self, url):
        """Split path of a URL into parts."""
        return self.split_path(urllib.parse.urlparse(url).path)

    @staticmethod
    def split_path(path):
        """Split path into parts."""
        return PurePosixPath(path).parts

    def get_query(self, url):
        """Return URL query as a dictionary."""
        return self.query_as_dict(urllib.parse.urlparse(url).query)

    @staticmethod
    def query_as_dict(query):
        """Convert query string into a dictionary.

        On repeated query variables, only the last one is returned.
        """
        return dict(urllib.parse.parse_qsl(query))

    def xpath_unique(self, doc, xpath_query):
        """Return exactly one xpath query result."""
        elements = doc.xpath(xpath_query)
        self.assert_(
            len(elements) == 1,
            'expect exactly one element: {}, {}',
            xpath_query,
            elements,
        )
        return elements[0]

    def xpath_maybe(self, doc, xpath_query):
        """Return an optional xpath query result."""
        elements = doc.xpath(xpath_query)
        self.assert_(
            len(elements) <= 1,
            'expect at most one element: {}, {}',
            xpath_query,
            elements,
        )
        return elements[0] if elements else None

    def xpath_some(self, doc, xpath_query):
        """Return some xpath query results."""
        elements = doc.xpath(xpath_query)
        self.assert_(elements, 'expect some elements: {}', xpath_query)
        return elements

    def get_text(self, element):
        return self.assert_.not_none(element.text)

    def __collect_text(self, pieces, root):

        def maybe_append(maybe_text):
            text = html.unescape(maybe_text or '').strip()
            if text:
                pieces.append(text)

        maybe_append(root.text)
        for child in root:
            self.__collect_text(pieces, child)
            maybe_append(child.tail)

    def get_text_recursively(self, root):
        """Unescape and join text of all elements, including root."""
        pieces = []
        self.__collect_text(pieces, self.assert_.not_none(root))
        return ' '.join(self.assert_.not_empty(pieces))

    def get_text_recursively_maybe(self, root):
        pieces = []
        self.__collect_text(pieces, self.assert_.not_none(root))
        return ' '.join(pieces)
