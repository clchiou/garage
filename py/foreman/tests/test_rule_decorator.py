import unittest

from pathlib import Path

import foreman
from foreman import Label, Loader, Searcher, rule


class RuleDecoratorTest(unittest.TestCase):

    def setUp(self):
        searcher = Searcher([Path('/somewhere')])
        self.loader = Loader(searcher)
        self.loader.path = Path('somewhere/pkg')
        self.__backup, foreman.LOADER = foreman.LOADER, self.loader

    def tearDown(self):
        foreman.LOADER = self.__backup

    def test_rule_decorator(self):

        @rule('some/rule/1')
        def build(_):
            """Some doc"""
            pass

        @rule
        def some_rule_2(_):
            """Some more doc"""
            pass

        @rule.depend('some/rule/1', 'when', 'configs')
        @rule.reverse_depend('some_rule_2', 'when', 'configs')
        @rule.annotate('name', 'value')
        def some_rule_3(_):
            pass

        rule_1 = self.loader.rules[Label.parse('//somewhere/pkg:some/rule/1')]
        self.assertEqual('Some doc', rule_1.doc)
        self.assertEqual([], rule_1.dependencies)
        self.assertEqual([], rule_1.reverse_dependencies)
        self.assertEqual({}, rule_1.annotations)

        rule_2 = self.loader.rules[Label.parse('//somewhere/pkg:some_rule_2')]
        self.assertEqual('Some more doc', rule_2.doc)
        self.assertEqual([], rule_2.dependencies)
        self.assertEqual([], rule_2.reverse_dependencies)
        self.assertEqual({}, rule_2.annotations)

        rule_3 = self.loader.rules[Label.parse('//somewhere/pkg:some_rule_3')]
        self.assertIsNone(rule_3.doc)

        self.assertEqual(1, len(rule_3.dependencies))
        self.assertEqual('some/rule/1', rule_3.dependencies[0].label)
        self.assertEqual('when', rule_3.dependencies[0].when)
        self.assertEqual('configs', rule_3.dependencies[0].configs)

        self.assertEqual(1, len(rule_3.reverse_dependencies))
        self.assertEqual('some_rule_2', rule_3.reverse_dependencies[0].label)
        self.assertEqual('when', rule_3.reverse_dependencies[0].when)
        self.assertEqual('configs', rule_3.reverse_dependencies[0].configs)

        self.assertEqual({'name': 'value'}, rule_3.annotations)


if __name__ == '__main__':
    unittest.main()
