import unittest

from foreman import ForemanError, Label, Parameter


class ParameterTest(unittest.TestCase):

    def test_parameter(self):
        p = Parameter(Label.parse('//x:y')).with_type(int).with_default(1)
        p.validate()

        p = Parameter(Label.parse('//x:y')).with_type(int).with_default('')
        with self.assertRaises(ForemanError):
            p.validate()

        p = (Parameter(Label.parse('//x:y'))
             .with_default('')
             .with_derive(lambda _: ''))
        with self.assertRaises(ForemanError):
            p.validate()


if __name__ == '__main__':
    unittest.main()
