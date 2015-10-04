import unittest

from contextlib import closing

from sqlalchemy import (
    MetaData,
    Column,
    ForeignKey,
    Integer,
    String,
    create_engine,
    select,
)

from garage import models
from garage.specs import base
from garage.specs import sql

import garage.specs.sql.tables  # as sql.tables
import garage.specs.sql.utils # as sql.utils


class SqlTest(unittest.TestCase):

    def test_iter_columns(self):
        m0 = (
            models.Model('m0', sql=sql.table_spec(name='t0'))
            .field('f0', sql=sql.column_spec(
                type=String, extra_attrs={'unique': True}))
            .field('f1', sql=sql.column_spec(
                is_primary_key=True, type=Integer))
        )

        m1 = (
            models.Model('m1', sql=sql.table_spec(name='t1'))
            .field('f0', sql=sql.column_spec(
                foreign_key_spec=sql.foreign_key_spec(model=m0)))
            .field('f1')
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

    def test_iter_junction_columns(self):

        def make_model(name):
            return (
                models.Model(name, sql=sql.table_spec(
                    name=name,
                    extra_columns=[
                        Column('f1', Integer, primary_key=True),
                    ],
                ))
                .field('f0', sql=sql.column_spec(
                    is_primary_key=True, type=Integer))
            )

        columns = list(sql.tables.iter_junction_columns([
            make_model(name) for name in ('t0', 't1', 't2')
        ]))
        self.assertEqual(3 * 2, len(columns))
        expect = [
            (0, 't0_f0', Integer),
            (1, 't0_f1', Integer),
            (2, 't1_f0', Integer),
            (3, 't1_f1', Integer),
            (4, 't2_f0', Integer),
            (5, 't2_f1', Integer),
        ]
        for i, name, type_cls in expect:
            self.assertEqual(name, columns[i].name)
            self.assertTrue(isinstance(columns[i].type, type_cls))
            self.assertTrue(columns[i].primary_key)

    def test_insert(self):
        model = (
            models.Model('model', sql=sql.table_spec(name='table'))
            .field('f0', sql=sql.column_spec(
                type=String, extra_attrs={'unique': True}))
            .field('f1', sql=sql.column_spec(
                type=Integer))
        )

        Obj = base.make_as_namespace(model)

        metadata = MetaData()
        table = sql.tables.make_table(model, metadata)
        engine = create_engine('sqlite://')
        metadata.create_all(engine)

        insert = sql.utils.make_insert(model)

        with closing(engine.connect()) as conn:

            # table.f0 is unique and 'x' is duplicated...
            insert(table, conn, [(Obj('x', 1), None)])
            insert(table, conn, [(Obj('x', 1), None)])
            insert(table, conn, [(Obj('x', 2), None)])
            insert(table, conn, [(Obj('y', 0), {'f1': 1})])

            query = select([table.c.f0, table.c.f1])
            with closing(conn.execute(query)) as result:
                objs = [tuple(item) for item in result]
            self.assertEqual(2, len(objs))
            self.assertSetEqual({('x', 1), ('y', 1)}, set(objs))


if __name__ == '__main__':
    unittest.main()
