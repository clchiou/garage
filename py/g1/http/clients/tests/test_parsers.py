import unittest

from lxml import etree

from g1.http import clients
from g1.http.clients import parsers


class TestError(Exception):
    pass


class ContextualParserTest(unittest.TestCase):

    def setUp(self):
        self.cp = parsers.ContextualParser(
            clients.Request('GET', 'http://example.com'), None
        )
        self.cp.ERROR_TYPE = TestError
        self.test_doc = etree.fromstring(
            '''
            <div>
                <h1>A</h1>
                <h2>B</h2>
                <h2>C</h2>
            </div>
            '''
        )

    def test_absolute_url(self):
        self.assertEqual(
            self.cp.absolute_url('/foo/bar.html'),
            'http://example.com/foo/bar.html',
        )
        self.assertEqual(
            self.cp.absolute_url('http://spam.egg/foo/bar.html'),
            'http://spam.egg/foo/bar.html',
        )
        # This also adds protocol to relative protocol URL.
        self.assertEqual(
            self.cp.absolute_url('//spam.egg/foo/bar.html'),
            'http://spam.egg/foo/bar.html',
        )

    def test_split_url_path(self):
        self.assertEqual(
            self.cp.split_url_path('http://example.com/foo/bar.html'),
            ('/', 'foo', 'bar.html'),
        )

    def test_split_path(self):
        self.assertEqual(
            self.cp.split_path('/foo/bar.html'),
            ('/', 'foo', 'bar.html'),
        )

    def test_get_query(self):
        self.assertEqual(
            self.cp.get_query('http://foo.com/?'),
            {},
        )
        self.assertEqual(
            self.cp.get_query('http://foo.com/?a=1&b=2&a=3&c=4'),
            {
                'a': '3',
                'b': '2',
                'c': '4',
            },
        )

    def test_query_as_dict(self):
        self.assertEqual(
            self.cp.query_as_dict(''),
            {},
        )
        self.assertEqual(
            self.cp.query_as_dict('a=1&b=2&a=3&c=4'),
            {
                'a': '3',
                'b': '2',
                'c': '4',
            },
        )

    def test_xpath_unique(self):
        element = self.cp.xpath_unique(self.test_doc, '//h1')
        self.assertIsNotNone(element)
        self.assertEqual(element.text, 'A')
        with self.assertRaisesRegex(TestError, r'expect exactly one'):
            self.cp.xpath_unique(self.test_doc, '//h2')

    def test_xpath_maybe(self):
        element = self.cp.xpath_maybe(self.test_doc, '//h1')
        self.assertIsNotNone(element)
        self.assertEqual(element.text, 'A')
        with self.assertRaisesRegex(TestError, r'expect at most one'):
            self.cp.xpath_maybe(self.test_doc, '//h2')
        self.assertIsNone(self.cp.xpath_maybe(self.test_doc, '//h3'))

    def test_xpath_some(self):
        elements = self.cp.xpath_some(self.test_doc, '//h2')
        self.assertEqual([e.text for e in elements], ['B', 'C'])
        with self.assertRaisesRegex(TestError, r'expect some'):
            self.cp.xpath_some(self.test_doc, '//h3')


if __name__ == '__main__':
    unittest.main()
