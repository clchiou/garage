import unittest
import unittest.mock

import datetime

from g1.asyncs import kernels
from g1.webs import consts
from g1.webs import wsgi_apps
from g1.webs.handlers import responses


class DefaultsTest(unittest.TestCase):

    NOW = datetime.datetime(2000, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    NOW_STR = responses.rfc_7231_date(NOW)

    def setUp(self):
        super().setUp()
        mock = unittest.mock.patch(responses.__name__ + '.datetimes').start()
        mock.utcnow.return_value = self.NOW
        self.handler = None
        self.response = None

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def assert_response(self, status, headers):
        self.assertIs(self.response.status, status)
        self.assertEqual(self.response.headers, headers)

    def assert_http_error(self, exc, status, headers, content=b''):
        self.assertIs(exc.status, status)
        self.assertEqual(exc.headers, headers)
        self.assertEqual(exc.content, content)

    def run_handler(self, headers):
        self.response = wsgi_apps._Response(None)
        self.response.headers.update(headers)
        kernels.run(
            self.handler(None, wsgi_apps.Response(self.response)),
            timeout=0.01,
        )

    @staticmethod
    async def noop(request, response):
        del request, response  # Unused.

    @staticmethod
    async def not_found(request, response):
        del request, response  # Unused.
        raise wsgi_apps.HttpError(consts.Statuses.NOT_FOUND, 'some error')

    @kernels.with_kernel
    def test_defaults(self):
        self.handler = responses.Defaults([('x', 'y')])
        self.run_handler([])
        self.assert_response(
            consts.Statuses.OK,
            {
                consts.HEADER_DATE: self.NOW_STR,
                'x': 'y',
            },
        )
        self.run_handler([(consts.HEADER_DATE, 'abc'), ('x', 'z')])
        self.assert_response(
            consts.Statuses.OK,
            {
                consts.HEADER_DATE: 'abc',
                'x': 'z',
            },
        )

    @kernels.with_kernel
    def test_error_headers(self):
        self.handler = responses.ErrorDefaults(self.not_found, [('x', 'y')])
        with self.assertRaises(wsgi_apps.HttpError) as cm:
            self.run_handler([])
        self.assert_http_error(
            cm.exception,
            consts.Statuses.NOT_FOUND,
            {
                consts.HEADER_DATE: self.NOW_STR,
                'x': 'y',
            },
        )
        with self.assertRaises(wsgi_apps.HttpError) as cm:
            self.run_handler([('x', 'z')])
        self.assert_http_error(
            cm.exception,
            consts.Statuses.NOT_FOUND,
            # response.headers are not copied to exc.headers, which
            # might be surprising but seems to be the right design.
            {
                consts.HEADER_DATE: self.NOW_STR,
                'x': 'y',
            },
        )

    @kernels.with_kernel
    def test_error_contents(self):
        self.handler = responses.ErrorDefaults(
            self.not_found,
            (),
            {consts.Statuses.NOT_FOUND: b'hello world'},
        )
        with self.assertRaises(wsgi_apps.HttpError) as cm:
            self.run_handler([])
        self.assert_http_error(
            cm.exception,
            consts.Statuses.NOT_FOUND,
            {consts.HEADER_DATE: self.NOW_STR},
            b'hello world',
        )

    @kernels.with_kernel
    def test_no_auto_date(self):
        self.handler = responses.Defaults((), auto_date=False)
        self.run_handler([])
        self.assert_response(consts.Statuses.OK, {})

        self.handler = responses.ErrorDefaults(
            self.not_found, (), auto_date=False
        )
        with self.assertRaises(wsgi_apps.HttpError) as cm:
            self.run_handler([])
        self.assert_http_error(cm.exception, consts.Statuses.NOT_FOUND, {})


class Rfc7231DateTest(unittest.TestCase):

    def test_rfc_7231_date(self):
        dt = datetime.datetime(
            2000, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc
        )
        self.assertEqual(
            responses.rfc_7231_date(dt),
            'Sun, 02 Jan 2000 03:04:05 GMT',
        )
        for month, month_str in zip(
            range(1, 12 + 1),
            [
                'Jan', 'Feb', 'Mar', \
                'Apr', 'May', 'Jun', \
                'Jul', 'Aug', 'Sep', \
                'Oct', 'Nov', 'Dec',
            ],
        ):
            self.assertIn(
                ', 02 %s 2000 03:04:05 GMT' % month_str,
                responses.rfc_7231_date(dt.replace(month=month)),
            )
        base_day_str_index = 6  # dt is on Sunday.
        day_strs = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for i in range(7):
            day = dt.day + i
            day_str = day_strs[(i + base_day_str_index) % 7]
            self.assertIn(
                '%s, %02d Jan 2000 03:04:05 GMT' % (day_str, day),
                responses.rfc_7231_date(dt.replace(day=day)),
            )


if __name__ == '__main__':
    unittest.main()
