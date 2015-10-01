import unittest

from sqlalchemy import ForeignKey, Integer, String

from garage import models
from garage.specs import sql

import garage.specs.sql.tables  # as sql.tables


class SqlTest(unittest.TestCase):

    def test_iter_columns(self):
        m0 = (
            models.Model('m0', sql=sql.table_spec(name='t0'))
            .field('f0', sql=sql.column_spec(
                type=String, extra_attrs={'unique': True}))
            .field('f1', sql=sql.column_spec(
                is_primary_key=True, is_natural_key=True, type=Integer))
        )

        m1 = (
            models.Model('m1', sql=sql.table_spec(name='t1'))
            .field('f0', sql=sql.column_spec(
                foreign_spec=sql.foreign_spec(
                    model=m0, cardinality=sql.ONE)))
            .field('f1', sql=sql.column_spec(
                foreign_spec=sql.foreign_spec(
                    model=m0, cardinality=sql.MANY)))
        )

        columns0 = list(sql.tables.iter_columns(m0))
        self.assertEqual(2, len(columns0))
        self.assertTrue(columns0[0].unique)
        self.assertTrue(isinstance(columns0[0].type, String))
        self.assertTrue(columns0[1].primary_key)
        self.assertTrue(isinstance(columns0[1].type, Integer))

        columns1 = list(sql.tables.iter_columns(m1))
        self.assertEqual(1, len(columns1))
        self.assertTrue(isinstance(columns1[0].type, Integer))
        foreign_keys = list(columns1[0].foreign_keys)
        self.assertEqual(1, len(foreign_keys))
        self.assertEqual('t0.f1', foreign_keys[0]._colspec)


if __name__ == '__main__':
    unittest.main()
