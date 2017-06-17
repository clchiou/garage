import unittest

from capnp import bases


class BasesTest(unittest.TestCase):

    def test_camel_to_upper_snake(self):
        for camel in ('http', 'HTTP', 'Http'):
            self.assertEqual('HTTP', bases.camel_to_upper_snake(camel))
        for camel in ('httpGet', 'HTTP_Get', 'http_Get', 'HttpGet'):
            self.assertEqual('HTTP_GET', bases.camel_to_upper_snake(camel))

        # Unfortunately it can't handle 'HTTPGet' because we don't know
        # how to write regex to split 'HTTP' from 'Get' (it needs to
        # understand that 'HTTP' is a word but 'HTTPG' is not).
        self.assertEqual('HTTPG_ET', bases.camel_to_upper_snake('HTTPGet'))

        self.assertEqual(
            'DO_XZ_ACTION', bases.camel_to_upper_snake('doXZaction'))
        self.assertEqual(
            'DO_ZACTION', bases.camel_to_upper_snake('doZaction'))

        self.assertEqual(
            'A_BC_DE_FG_H', bases.camel_to_upper_snake('aBcDeFgH'))

        self.assertEqual(
            'A_PICTURE_IS_WORTH_A_THOUSAND_WORDS',
            bases.camel_to_upper_snake('aPICTUREisWORTHaTHOUSANDwords'),
        )

    def test_snake_to_lower_camel(self):
        self.assertEqual('camelCase', bases.snake_to_lower_camel('CAMEL_CASE'))
        self.assertEqual('camelCase', bases.snake_to_lower_camel('camel_case'))
        self.assertEqual('http', bases.snake_to_lower_camel('HTTP'))
        self.assertEqual('http', bases.snake_to_lower_camel('http'))
        self.assertEqual('httpGet', bases.snake_to_lower_camel('HTTP_GET'))
        self.assertEqual('httpGet', bases.snake_to_lower_camel('http_get'))


if __name__ == '__main__':
    unittest.main()
