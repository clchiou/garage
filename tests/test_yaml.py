import unittest

import collections
import datetime

import yaml

from garage.collections import ImmutableSortedDict
from garage.timezones import TimeZone
from garage.yaml import represent_datetime
from garage.yaml import represent_mapping


class YamlTest(unittest.TestCase):

    def setUp(self):
        self.yaml_representers = yaml.SafeDumper.yaml_representers.copy()
        self.yaml_multi_representers = \
            yaml.SafeDumper.yaml_multi_representers.copy()

    def tearDown(self):
        yaml.SafeDumper.yaml_representers = self.yaml_representers
        yaml.SafeDumper.yaml_multi_representers = \
            self.yaml_multi_representers

    def test_no_representers(self):
        mapping = ImmutableSortedDict(c=3, a=1, b=2)
        with self.assertRaises(yaml.representer.RepresenterError):
            yaml.safe_dump(mapping)

    def test_representers(self):
        yaml.SafeDumper.add_representer(
            ImmutableSortedDict, represent_mapping)
        yaml.SafeDumper.add_representer(
            datetime.datetime, represent_datetime)
        self.call_safe_dump_datetime()
        self.call_safe_dump_mapping()

    def test_multi_representers(self):
        yaml.SafeDumper.add_multi_representer(
            collections.Mapping, represent_mapping)
        self.call_safe_dump_mapping()

    def call_safe_dump_datetime(self):
        dt = datetime.datetime(2000, 1, 2, 3, 4, 5, 6, TimeZone.UTC)
        dt_yaml = '2000-01-02T03:04:05.000006+00:00\n...\n'
        self.assertEqual(dt_yaml, yaml.safe_dump(dt))

    def call_safe_dump_mapping(self):
        mapping = ImmutableSortedDict(c=3, a=1, b=2)
        mapping_yaml_flow = '{a: 1, b: 2, c: 3}\n'
        mapping_yaml = 'a: 1\nb: 2\nc: 3\n'
        self.assertEqual(
            mapping_yaml_flow,
            yaml.safe_dump(mapping, default_flow_style=True),
        )
        self.assertEqual(
            mapping_yaml,
            yaml.safe_dump(mapping, default_flow_style=False),
        )


if __name__ == '__main__':
    unittest.main()
