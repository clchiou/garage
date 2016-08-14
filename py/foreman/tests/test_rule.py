import unittest

from foreman import Label, Rule


class RuleTest(unittest.TestCase):

    def test_rule(self):
        r = (
            Rule(Label.parse('//x:a'))
            .depend('b', configs={
                'c': 1,
                '//y:c': 2,
            })
            .depend('//y:c')
        )
        r.parse_labels(r.label.path)

        self.assertEqual(Label.parse('//x:b'), r.dependencies[0].label)
        self.assertEqual(
            {
                Label.parse('//x:c'): 1,
                Label.parse('//y:c'): 2,
            },
            r.dependencies[0].configs,
        )
        self.assertEqual(Label.parse('//y:c'), r.dependencies[1].label)
        self.assertIsNone(r.dependencies[1].configs)


if __name__ == '__main__':
    unittest.main()
