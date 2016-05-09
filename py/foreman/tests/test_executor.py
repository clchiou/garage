import unittest

from foreman import (

    Label,
    Parameter,
    Rule,
    Things,

    BuildIds,
    ParameterValues,
)


class BuildIdsTest(unittest.TestCase):

    def test_build_ids(self):

        label = Label.parse('//x:r')
        rule = Rule(label)

        build_ids = BuildIds()

        env = {}
        self.assertFalse(build_ids.check_and_add(rule, env))
        self.assertTrue(build_ids.check_and_add(rule, env))

        env[Label.parse('//y:p0')] = 1
        self.assertFalse(build_ids.check_and_add(rule, env))
        self.assertTrue(build_ids.check_and_add(rule, env))

        env[Label.parse('//y:p0')] = 2
        self.assertFalse(build_ids.check_and_add(rule, env))
        self.assertTrue(build_ids.check_and_add(rule, env))


class ParameterValuesTest(unittest.TestCase):

    def test_parameter_values(self):

        label0 = Label.parse('//x:p0')
        par0 = Parameter(label0).with_default(10)

        label1 = Label.parse('//x:p1')
        par1 = Parameter(label1).with_derive(lambda ps: ps['//x:p0'] + 2)

        label2 = Label.parse('//x:p2')
        par2 = Parameter(label2)

        parameters = Things()
        parameters[label0] = par0
        parameters[label1] = par1
        parameters[label2] = par2

        ps = ParameterValues(
            parameters,
            {label2: 'hello'},
            Label.parse('//y:y').path,
        )
        self.assertEqual(10, ps['//x:p0'])
        self.assertEqual(12, ps['//x:p1'])
        self.assertEqual('hello', ps['//x:p2'])


if __name__ == '__main__':
    unittest.main()
