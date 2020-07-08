import unittest

import itertools

import sqlalchemy

from g1.databases import sqlite
from g1.operations.databases.bases import interfaces
from g1.operations.databases.servers import databases
from g1.operations.databases.servers import schemas

K1_NEXT = interfaces.next_key(b'k1')

SORT_BY_REVISION = interfaces.Sort(
    sort_by=interfaces.SortBys.REVISION,
    ascending=True,
)

SORT_BY_KEY = interfaces.Sort(
    sort_by=interfaces.SortBys.KEY,
    ascending=True,
)

SORT_BY_KEY_DESC = interfaces.Sort(
    sort_by=interfaces.SortBys.KEY,
    ascending=False,
)

SORT_BY_VALUE = interfaces.Sort(
    sort_by=interfaces.SortBys.VALUE,
    ascending=True,
)


def extract_keyspace(revisions):
    keyspace = list(_extract_keyspace(revisions))
    keyspace.sort(key=lambda kv: (kv.revision, kv.key))
    return keyspace


def _extract_keyspace(revisions):
    for _, g in itertools.groupby(
        sorted(revisions, key=lambda kv: (kv.key, -kv.revision)),
        lambda kv: kv.key,
    ):
        try:
            pair = next(g)
        except StopIteration:
            raise AssertionError('expect non-empty group')
        if pair.value:
            yield pair


def ko(r, k):
    return interfaces.KeyOnly(revision=r, key=k)


def kv(r, k, v):
    return interfaces.KeyValue(revision=r, key=k, value=v)


def lease_(l, e, ks):
    return interfaces.Lease(lease=l, expiration=e, keys=ks)


class DatabasesTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.engine = sqlite.create_engine('sqlite://')
        metadata = sqlalchemy.MetaData()
        self.tables = schemas.make_tables(metadata)
        metadata.create_all(self.engine)

    def assert_revisions(self, revisions, keyspace=None, revision=None):

        def list_table(table):
            result = self.engine.execute(
                sqlalchemy.select([
                    table.c.revision,
                    table.c.key,
                    table.c.value,
                ])\
                .order_by(table.c.revision, table.c.key)
            )
            try:
                return [
                    interfaces.KeyValue(
                        revision=row[0], key=row[1], value=row[2]
                    ) for row in result
                ]
            finally:
                result.close()

        self.assertEqual(list_table(self.tables.revisions), revisions)
        self.assertEqual(
            list_table(self.tables.keyspace),
            extract_keyspace(revisions) if keyspace is None else keyspace,
        )
        if revision is None and revisions:
            revision = max(revisions, key=lambda kv: kv.revision).revision
        if revision is not None:
            self.assertEqual(
                databases.get_revision(self.engine, self.tables),
                revision,
            )

    def assert_leases(self, leases, num_leases_key_ids):
        self.assertEqual(
            databases.lease_scan(
                self.engine,
                self.tables,
                lease_start=0,
                lease_end=0,
                limit=0,
            ),
            leases,
        )
        self.assertEqual(
            self.engine.execute(
                sqlalchemy.select([sqlalchemy.func.count()])\
                .select_from(self.tables.leases)
            ).scalar(),
            len(leases),
        )
        self.assertEqual(
            self.engine.execute(
                sqlalchemy.select([sqlalchemy.func.count()])\
                .select_from(self.tables.leases_key_ids)
            ).scalar(),
            num_leases_key_ids,
        )

    def make_kv_testdata(self):
        d = lambda i, r, k, v: {
            'key_id': i,
            'revision': r,
            'key': k,
            'value': v,
        }
        self.engine.execute(
            self.tables.keyspace.insert(),
            [
                d(1, 4, b'k1', b'v3'),
                d(2, 5, b'k2', b'v4'),
            ],
        )
        d = lambda r, k, v: {'revision': r, 'key': k, 'value': v}
        self.engine.execute(
            self.tables.revisions.insert(),
            [
                d(1, b'k1', b'v1'),
                d(2, b'k1', b'v2'),
                d(3, b'k1', None),
                d(4, b'k1', b'v3'),
                d(5, b'k2', b'v4'),
                d(6, b'k3', b'v5'),
                d(7, b'k3', None),
            ],
        )
        self.engine.execute(
            self.tables.current_revision.insert().values(revision=7)
        )
        d = lambda l, e: {'lease': l, 'expiration': e}
        self.engine.execute(
            self.tables.leases.insert(),
            [
                d(1001, 10001),
                d(1002, 10002),
                d(1003, 10003),
                d(1004, 10004),
                d(1005, 10005),
                d(1006, 10006),
            ],
        )
        d = lambda l, k: {'lease': l, 'key_id': k}
        self.engine.execute(
            self.tables.leases_key_ids.insert(),
            [
                d(1001, 1),
                d(1002, 2),
                d(1003, 1),
                d(1004, 2),
                d(1005, 1),
                d(1006, 2),
            ],
        )

    def make_lease_testdata(self):
        d = lambda i, r, k, v: {
            'key_id': i,
            'revision': r,
            'key': k,
            'value': v,
        }
        self.engine.execute(
            self.tables.keyspace.insert(),
            [d(i, i, b'k%d' % i, b'x') for i in range(1, 11)],
        )
        d = lambda r, k, v: {'revision': r, 'key': k, 'value': v}
        self.engine.execute(
            self.tables.revisions.insert(),
            [d(i, b'k%d' % i, b'x') for i in range(1, 11)],
        )
        self.engine.execute(
            self.tables.current_revision.insert().values(revision=10)
        )
        d = lambda l, e: {'lease': l, 'expiration': e}
        self.engine.execute(
            self.tables.leases.insert(),
            [
                d(1001, 10001),
                d(1002, 10002),
                d(1003, 10003),
                d(1004, 10004),
                d(1005, 10005),
            ],
        )
        d = lambda l, k: {'lease': l, 'key_id': k}
        self.engine.execute(
            self.tables.leases_key_ids.insert(),
            [
                # Lease 1001.
                d(1001, 5),
                d(1001, 2),
                d(1001, 1),
                d(1001, 4),
                d(1001, 3),
                # Lease 1002.
                d(1002, 5),
                d(1002, 4),
                d(1002, 3),
                d(1002, 6),
                # Lease 1003 (empty).
                # Lease 1004.
                d(1004, 5),
                d(1004, 1),
                d(1004, 13),  # Non-existent key_id.
                d(1004, 9),
                # Lease 1005.
                d(1005, 2),
                d(1005, 11),  # Non-existent key_id.
                d(1005, 8),
                d(1005, 5),
            ],
        )

    def test_current_revision(self):

        def list_table():
            result = self.engine.execute(self.tables.current_revision.select())
            try:
                return sorted(row[0] for row in result)
            finally:
                result.close()

        def get():
            return databases.get_revision(self.engine, self.tables)

        def inc(r):
            databases.increment_revision(self.engine, self.tables, revision=r)

        self.assertEqual(list_table(), [])
        self.assertEqual(get(), 0)
        for revision in range(10):
            with self.subTest(revision):
                for _ in range(4):
                    inc(revision)  # `increment_revision` is idempotent.
                self.assertEqual(list_table(), [revision + 1])
                self.assertEqual(get(), revision + 1)

        with self.assertRaisesRegex(AssertionError, r'expect x == 6, not 10'):
            inc(5)

        # Make sure that `get_revision` raises when the current_revision
        # table has more than one row.
        self.engine.execute(
            self.tables.current_revision.insert().values(revision=3)
        )
        self.assertEqual(list_table(), [3, 10])
        with self.assertRaisesRegex(AssertionError, r'expect None, not'):
            get()

    def test_get_key_id(self):
        self.assertIsNone(
            databases._get_key_id(self.engine, self.tables, key=b'k1')
        )
        self.make_kv_testdata()
        self.assertEqual(
            databases._get_key_id(self.engine, self.tables, key=b'k1'), 1
        )

    def test_get(self):

        def get(r, k):
            return databases.get(self.engine, self.tables, revision=r, key=k)

        self.assertIsNone(get(0, b'k1'))
        self.assertIsNone(get(1, b'k1'))

        self.make_kv_testdata()

        self.assertEqual(get(0, b'k1'), kv(4, b'k1', b'v3'))
        self.assertEqual(get(2, b'k1'), kv(2, b'k1', b'v2'))
        self.assertIsNone(get(3, b'k1'))  # Tombstone.
        self.assertEqual(get(4, b'k1'), kv(4, b'k1', b'v3'))

        self.assertIsNone(get(0, b'no-such-key'))
        self.assertIsNone(get(1, b'no-such-key'))

    def test_count(self):

        def count(r=0, ks=b'', ke=b''):
            return databases.count(
                self.engine,
                self.tables,
                revision=r,
                key_start=ks,
                key_end=ke,
            )

        self.assertEqual(count(), 0)
        self.make_kv_testdata()
        self.assertEqual(count(), 2)
        self.assertEqual(count(r=1), 1)
        self.assertEqual(count(ks=b'k1', ke=K1_NEXT), 1)
        self.assertEqual(count(r=1, ks=b'k1', ke=K1_NEXT), 1)

    def test_scan_keys(self):

        def scan_keys(r=0, ks=b'', ke=b'', s=(SORT_BY_REVISION, ), l=0):
            return databases.scan_keys(
                self.engine,
                self.tables,
                revision=r,
                key_start=ks,
                key_end=ke,
                sorts=s,
                limit=l,
            )

        self.assertEqual(scan_keys(), [])
        self.make_kv_testdata()
        self.assertEqual(scan_keys(), [ko(4, b'k1'), ko(5, b'k2')])
        self.assertEqual(scan_keys(r=1), [ko(1, b'k1')])
        self.assertEqual(scan_keys(r=3), [])
        self.assertEqual(scan_keys(r=4), [ko(4, b'k1')])
        self.assertEqual(scan_keys(r=5), [ko(4, b'k1'), ko(5, b'k2')])
        self.assertEqual(
            scan_keys(r=6),
            [
                ko(4, b'k1'),
                ko(5, b'k2'),
                ko(6, b'k3'),
            ],
        )
        self.assertEqual(scan_keys(r=7), [ko(4, b'k1'), ko(5, b'k2')])

        self.assertEqual(scan_keys(ks=b'k1', ke=K1_NEXT), [ko(4, b'k1')])
        self.assertEqual(scan_keys(r=1, ks=b'k1', ke=K1_NEXT), [ko(1, b'k1')])
        self.assertEqual(
            scan_keys(r=6, s=[SORT_BY_KEY_DESC, SORT_BY_REVISION], l=3),
            [
                ko(6, b'k3'),
                ko(5, b'k2'),
                ko(4, b'k1'),
            ],
        )

    def test_scan(self):

        def scan(r=0, ks=b'', ke=b'', s=(SORT_BY_REVISION, ), l=0):
            return databases.scan(
                self.engine,
                self.tables,
                revision=r,
                key_start=ks,
                key_end=ke,
                sorts=s,
                limit=l,
            )

        self.assertEqual(scan(), [])
        self.make_kv_testdata()
        self.assertEqual(scan(), [kv(4, b'k1', b'v3'), kv(5, b'k2', b'v4')])
        self.assertEqual(
            scan(r=1, s=[SORT_BY_VALUE, SORT_BY_REVISION]),
            [kv(1, b'k1', b'v1')],
        )
        self.assertEqual(scan(ks=b'k1', ke=K1_NEXT), [kv(4, b'k1', b'v3')])
        self.assertEqual(scan(r=1, ks=b'k99'), [])
        self.assertEqual(
            scan(r=6, s=[SORT_BY_KEY_DESC, SORT_BY_REVISION], l=2),
            [kv(6, b'k3', b'v5'), kv(5, b'k2', b'v4')],
        )

    def test_set_and_delete(self):

        def set_(k, v):
            return databases.set_(self.engine, self.tables, key=k, value=v)

        def delete(ks, ke):
            return databases.delete(
                self.engine,
                self.tables,
                key_start=ks,
                key_end=ke,
            )

        revisions = []
        self.assert_revisions(revisions)

        self.assertIsNone(set_(b'k1', b'v1'))
        revisions.append(kv(1, b'k1', b'v1'))
        self.assert_revisions(revisions)

        # `set_` is idempotent.
        self.assertEqual(set_(b'k1', b'v1'), kv(1, b'k1', b'v1'))
        self.assert_revisions(revisions)

        self.assertIsNone(set_(b'k2', b'v2'))
        revisions.append(kv(2, b'k2', b'v2'))
        self.assert_revisions(revisions)

        self.assertEqual(set_(b'k1', b'v3'), kv(1, b'k1', b'v1'))
        revisions.append(kv(3, b'k1', b'v3'))
        self.assert_revisions(revisions)

        self.assertIsNone(set_(b'k3', b'v4'))
        revisions.append(kv(4, b'k3', b'v4'))
        self.assert_revisions(revisions)

        self.assertEqual(
            delete(b'k1', b'k3'),
            [kv(3, b'k1', b'v3'), kv(2, b'k2', b'v2')],
        )
        revisions.append(kv(5, b'k1', None))
        revisions.append(kv(5, b'k2', None))
        self.assert_revisions(revisions)

        # `delete` is idempotent.
        self.assertEqual(delete(b'k1', b'k3'), [])
        self.assert_revisions(revisions)

        self.assertIsNone(set_(b'k1', b'v5'))
        revisions.append(kv(6, b'k1', b'v5'))
        self.assert_revisions(revisions)

        self.assertIsNone(set_(b'k4', b'v6'))
        revisions.append(kv(7, b'k4', b'v6'))
        self.assert_revisions(revisions)

        self.assertEqual(
            delete(b'', b''),
            [
                kv(4, b'k3', b'v4'),
                kv(6, b'k1', b'v5'),
                kv(7, b'k4', b'v6'),
            ],
        )
        revisions.append(kv(8, b'k1', None))
        revisions.append(kv(8, b'k3', None))
        revisions.append(kv(8, b'k4', None))
        self.assert_revisions(revisions)

        self.assertIsNone(set_(b'k1', b'v7'))
        revisions.append(kv(9, b'k1', b'v7'))
        self.assert_revisions(revisions)

    def test_lease_scan(self):

        def lease_get(l):
            return databases.lease_get(self.engine, self.tables, lease=l)

        def lease_count(ls=0, le=0):
            return databases.lease_count(
                self.engine,
                self.tables,
                lease_start=ls,
                lease_end=le,
            )

        def lease_scan(ls=0, le=0, l=0):
            return databases.lease_scan(
                self.engine,
                self.tables,
                lease_start=ls,
                lease_end=le,
                limit=l,
            )

        def lease_revoke(l):
            return databases.lease_revoke(self.engine, self.tables, lease=l)

        self.assertIsNone(lease_get(1001))
        self.assertEqual(lease_count(), 0)
        self.assertEqual(lease_scan(), [])

        self.make_lease_testdata()
        self.assert_revisions([kv(i, b'k%d' % i, b'x') for i in range(1, 11)])

        self.assertEqual(
            lease_get(1001),
            lease_(1001, 10001, (b'k1', b'k2', b'k3', b'k4', b'k5')),
        )

        self.assertEqual(lease_count(), 5)
        self.assertEqual(lease_count(ls=1004), 2)

        self.assertEqual(
            lease_scan(l=3),
            [
                lease_(1001, 10001, (b'k1', b'k2', b'k3', b'k4', b'k5')),
                lease_(1002, 10002, (b'k3', b'k4', b'k5', b'k6')),
                lease_(1003, 10003, ()),
            ],
        )
        self.assertEqual(
            lease_scan(ls=1004),
            [
                lease_(1004, 10004, (b'k1', b'k5', b'k9')),
                lease_(1005, 10005, (b'k2', b'k5', b'k8')),
            ],
        )

        lease_revoke(1001)
        self.assertEqual(
            lease_scan(),
            [
                lease_(1002, 10002, (b'k3', b'k4', b'k5', b'k6')),
                lease_(1003, 10003, ()),
                lease_(1004, 10004, (b'k1', b'k5', b'k9')),
                lease_(1005, 10005, (b'k2', b'k5', b'k8')),
            ],
        )

    def test_lease_grant_and_revoke(self):

        def lease_get(l):
            return databases.lease_get(self.engine, self.tables, lease=l)

        def lease_grant(l, e):
            return databases.lease_grant(
                self.engine, self.tables, lease=l, expiration=e
            )

        def lease_revoke(l):
            return databases.lease_revoke(self.engine, self.tables, lease=l)

        l = lease_get(1001)
        self.assertIsNone(l)

        self.assertEqual(lease_grant(1001, 10001), l)
        l = lease_get(1001)
        self.assertEqual(l, lease_(1001, 10001, ()))

        # `lease_grant` is idempotent.
        self.assertEqual(lease_grant(1001, 10011), l)
        l = lease_get(1001)
        self.assertEqual(l, lease_(1001, 10011, ()))

        self.assertEqual(lease_grant(1001, 999), l)
        l = lease_get(1001)
        self.assertEqual(l, lease_(1001, 999, ()))

        self.assertEqual(lease_revoke(1001), l)
        l = lease_get(1001)
        self.assertIsNone(l)

        # `lease_revoke` is idempotent.
        self.assertIsNone(lease_revoke(1001))

        self.assertEqual(lease_grant(1001, 50), l)
        l = lease_get(1001)
        self.assertEqual(l, lease_(1001, 50, ()))

    def test_lease_associate_and_dissociate(self):

        def lease_get(l):
            return databases.lease_get(self.engine, self.tables, lease=l)

        def lease_associate(l, k):
            return databases.lease_associate(
                self.engine, self.tables, lease=l, key=k
            )

        def lease_dissociate(l, k):
            return databases.lease_dissociate(
                self.engine, self.tables, lease=l, key=k
            )

        self.make_lease_testdata()

        with self.assertRaises(interfaces.LeaseNotFoundError):
            lease_associate(9999, b'k1')
        with self.assertRaises(interfaces.KeyNotFoundError):
            lease_associate(1001, b'no-such-key')
        with self.assertRaises(interfaces.LeaseNotFoundError):
            lease_dissociate(9999, b'k1')
        with self.assertRaises(interfaces.KeyNotFoundError):
            lease_dissociate(1001, b'no-such-key')

        l = lease_get(1003)
        self.assertEqual(l, lease_(1003, 10003, ()))

        self.assertEqual(lease_associate(1003, b'k1'), l)
        l = lease_get(1003)
        self.assertEqual(l, lease_(1003, 10003, (b'k1', )))

        # `lease_associate` is idempotent.
        self.assertEqual(lease_associate(1003, b'k1'), l)

        self.assert_leases(
            [
                lease_(1001, 10001, (b'k1', b'k2', b'k3', b'k4', b'k5')),
                lease_(1002, 10002, (b'k3', b'k4', b'k5', b'k6')),
                lease_(1003, 10003, (b'k1', )),
                lease_(1004, 10004, (b'k1', b'k5', b'k9')),
                lease_(1005, 10005, (b'k2', b'k5', b'k8')),
            ],
            18,  # 1 + 15 + 2 non-existent key_id.
        )

        self.assertEqual(lease_dissociate(1003, b'k1'), l)
        l = lease_get(1003)
        self.assertEqual(l, lease_(1003, 10003, ()))

        # `lease_dissociate` is idempotent.
        self.assertEqual(lease_dissociate(1003, b'k1'), l)

        self.assertEqual(lease_dissociate(1003, b'k5'), l)

        self.assert_leases(
            [
                lease_(1001, 10001, (b'k1', b'k2', b'k3', b'k4', b'k5')),
                lease_(1002, 10002, (b'k3', b'k4', b'k5', b'k6')),
                lease_(1003, 10003, ()),
                lease_(1004, 10004, (b'k1', b'k5', b'k9')),
                lease_(1005, 10005, (b'k2', b'k5', b'k8')),
            ],
            17,  # 15 + 2 non-existent key_id.
        )

    def test_lease_expire(self):

        def assert_before_expire():
            self.assert_revisions(
                [kv(i, b'k%d' % i, b'x') for i in range(1, 11)],
                [kv(i, b'k%d' % i, b'x') for i in range(1, 11)],
                10,
            )
            self.assert_leases(
                [
                    lease_(1001, 10001, (b'k1', b'k2', b'k3', b'k4', b'k5')),
                    lease_(1002, 10002, (b'k3', b'k4', b'k5', b'k6')),
                    lease_(1003, 10003, ()),
                    lease_(1004, 10004, (b'k1', b'k5', b'k9')),
                    lease_(1005, 10005, (b'k2', b'k5', b'k8')),
                ],
                17,  # 15 + 2 non-existent key_id.
            )

        def assert_after_expire():
            self.assert_revisions(
                [kv(i, b'k%d' % i, b'x') for i in range(1, 11)] +
                [kv(11, b'k%d' % i, None) for i in range(1, 6 + 1)],
                [
                    kv(7, b'k7', b'x'),
                    kv(8, b'k8', b'x'),
                    kv(9, b'k9', b'x'),
                    kv(10, b'k10', b'x'),
                ],
                11,
            )
            self.assert_leases(
                [
                    lease_(1004, 10004, (b'k9', )),
                    lease_(1005, 10005, (b'k8', )),
                ],
                4,  # 2 + 2 non-existent key_id.
            )

        self.make_lease_testdata()
        assert_before_expire()
        self.assertEqual(
            databases.lease_expire(self.engine, self.tables, current_time=999),
            [],
        )
        assert_before_expire()

        self.assertEqual(
            sorted(
                databases.lease_expire(
                    self.engine, self.tables, current_time=10004
                ),
                key=lambda kv: kv.revision,
            ),
            [kv(i, b'k%d' % i, b'x') for i in range(1, 6 + 1)],
        )
        assert_after_expire()
        self.assertEqual(
            databases.lease_expire(
                self.engine, self.tables, current_time=10004
            ),
            [],
        )
        assert_after_expire()

    def test_compact(self):
        self.make_kv_testdata()
        self.assert_revisions(
            [
                kv(1, b'k1', b'v1'),
                kv(2, b'k1', b'v2'),
                kv(3, b'k1', None),
                kv(4, b'k1', b'v3'),
                kv(5, b'k2', b'v4'),
                kv(6, b'k3', b'v5'),
                kv(7, b'k3', None),
            ],
            [
                kv(4, b'k1', b'v3'),
                kv(5, b'k2', b'v4'),
            ],
            7,
        )

        databases.compact(self.engine, self.tables, revision=5)
        self.assert_revisions(
            [
                kv(5, b'k2', b'v4'),
                kv(6, b'k3', b'v5'),
                kv(7, b'k3', None),
            ],
            [
                kv(4, b'k1', b'v3'),
                kv(5, b'k2', b'v4'),
            ],
            7,
        )

        databases.compact(self.engine, self.tables, revision=999)
        self.assert_revisions(
            [],
            [
                kv(4, b'k1', b'v3'),
                kv(5, b'k2', b'v4'),
            ],
            7,
        )


class ExtractKeyspaceTest(unittest.TestCase):

    def test_extract_keyspace(self):
        self.assertEqual(extract_keyspace([]), [])
        self.assertEqual(
            extract_keyspace([kv(1, b'k1', b'v1')]),
            [kv(1, b'k1', b'v1')],
        )
        self.assertEqual(
            extract_keyspace([
                kv(1, b'k1', b'v1'),
                kv(2, b'k2', b'v2'),
            ]),
            [kv(1, b'k1', b'v1'), kv(2, b'k2', b'v2')],
        )
        self.assertEqual(
            extract_keyspace([
                kv(4, b'k2', b'v3'),
                kv(1, b'k1', b'v1'),
                kv(3, b'k1', None),
                kv(2, b'k2', b'v2'),
            ]),
            [kv(4, b'k2', b'v3')],
        )


if __name__ == '__main__':
    unittest.main()
