import unittest

from g1.bases import cases


class CasesTest(unittest.TestCase):

    def test_cases(self):

        self.assertEqual(cases.camel_to_lower_snake('httpGet'), 'http_get')
        self.assertEqual(cases.camel_to_lower_snake('HttpGet'), 'http_get')
        self.assertEqual(cases.camel_to_lower_snake('HTTPGet'), 'http_get')
        self.assertEqual(cases.camel_to_lower_snake('_httpGet_'), '_http_get_')
        self.assertEqual(cases.camel_to_lower_snake('_HttpGet_'), '_http_get_')
        self.assertEqual(cases.camel_to_lower_snake('HTTP2Get'), 'http2_get')
        self.assertEqual(cases.camel_to_lower_snake('bootG'), 'boot_g')
        self.assertEqual(cases.camel_to_lower_snake('BootG'), 'boot_g')

        # TODO: Sadly, current regex-based implementation generates some
        # weird conversion results.
        self.assertEqual(cases.camel_to_lower_snake('HTTPget'), 'htt_pget')
        self.assertEqual(cases.camel_to_lower_snake('bootGG'), 'bootg_g')

        self.assertEqual(
            cases.lower_snake_to_lower_camel('http_get'), 'httpGet'
        )
        self.assertEqual(
            cases.lower_snake_to_lower_camel('get_2_items'), 'get2Items'
        )
        self.assertEqual(
            cases.lower_snake_to_lower_camel('_http_get_'), '_httpGet_'
        )
        self.assertEqual(
            cases.lower_snake_to_lower_camel('__http__get__'), '__httpGet__'
        )
        with self.assertRaisesRegex(AssertionError, r'expect.*islower'):
            cases.lower_snake_to_lower_camel('HTTP_GET')

        self.assertEqual(
            cases.lower_snake_to_upper_camel('http_get'), 'HttpGet'
        )
        self.assertEqual(
            cases.lower_snake_to_upper_camel('get_2_items'), 'Get2Items'
        )
        self.assertEqual(
            cases.lower_snake_to_upper_camel('_http_get_'), '_HttpGet_'
        )
        self.assertEqual(
            cases.lower_snake_to_upper_camel('__http__get__'), '__HttpGet__'
        )
        with self.assertRaisesRegex(AssertionError, r'expect.*islower'):
            cases.lower_snake_to_upper_camel('HTTP_GET')

        self.assertEqual(cases.upper_to_lower_camel('HttpGet'), 'httpGet')
        self.assertEqual(cases.upper_to_lower_camel('__HttpGet'), '__httpGet')


if __name__ == '__main__':
    unittest.main()
