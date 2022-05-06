import unittest

import re

import sqlalchemy

from g1.databases import sqlite
from g1.operations.databases.bases import interfaces
from g1.operations.databases.servers import queries
from g1.operations.databases.servers import schemas


class QueriesTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.engine = sqlite.create_engine('sqlite://')
        metadata = sqlalchemy.MetaData()
        self.tables = schemas.make_tables(metadata)
        metadata.create_all(self.engine)

    def assert_query_regex(self, query, expect):
        self.assertRegex(
            re.sub(r'\s+', ' ', str(query)),
            re.sub(r'\s+', ' ', expect).strip(),
        )

    def test_get_revision(self):
        self.assert_query_regex(
            queries.get_revision(self.tables),
            r'''
            SELECT
                current_revision.revision
            FROM
                current_revision
            ''',
        )

    def test_increment_revision(self):
        self.assert_query_regex(
            queries.increment_revision(self.tables, revision=0),
            r'''
            INSERT OR REPLACE INTO
                current_revision
                \(revision\)
            VALUES
                \(:revision\)
            ''',
        )
        self.assert_query_regex(
            queries.increment_revision(self.tables, revision=1),
            r'''
            UPDATE
                current_revision
            SET
                revision=:revision
            WHERE
                current_revision.revision = :revision_1
            ''',
        )

    def test_get_key_id(self):
        self.assert_query_regex(
            queries.get_key_id(self.tables, key=b'x'),
            r'''
            SELECT
                keyspace.key_id
            FROM
                keyspace
            WHERE
                keyspace.key = :key_1
            ''',
        )

    def test_get(self):
        self.assert_query_regex(
            queries.get(self.tables, revision=0, key=b'x'),
            r'''
            SELECT
                keyspace.revision,
                keyspace.key,
                keyspace.value
            FROM
                keyspace
            WHERE
                keyspace.key = :key_1
            ''',
        )
        self.assert_query_regex(
            queries.get(self.tables, revision=1, key=b'x'),
            r'''
            SELECT
                revisions.revision,
                revisions.key,
                revisions.value
            FROM
                revisions
            WHERE
                revisions.revision <= :revision_1 AND
                revisions.key = :key_1
            ORDER BY
                revisions.revision DESC
            ''',
        )

    def test_count(self):
        self.assert_query_regex(
            queries.count(
                self.tables,
                revision=0,
                key_start=b'',
                key_end=b'x',
            ),
            r'''
            SELECT
                count\(\*\) AS count_1
            FROM
                keyspace
            WHERE
                keyspace.key < :key_1
            ''',
        )
        self.assert_query_regex(
            queries.count(
                self.tables,
                revision=1,
                key_start=b'',
                key_end=b'x',
            ),
            r'''
            SELECT
                count\(\*\) AS count_1
            FROM
                revisions
            JOIN
                \(SELECT
                    max\(revisions.revision\) AS revision,
                    revisions.key AS key
                FROM
                    revisions
                WHERE
                    revisions.revision <= :revision_1
                GROUP BY
                    revisions.key\)
                AS
                    _last_revisions
            ON
                revisions.revision = _last_revisions.revision AND
                revisions.key = _last_revisions.key
            WHERE
                revisions.key < :key_1 AND
                revisions.value IS NOT NULL
            ''',
        )

    def test_scan_keys(self):
        self.assert_query_regex(
            queries.scan_keys(
                self.tables,
                revision=0,
                key_start=b'',
                key_end=b'',
                sorts=(),
                limit=0,
            ),
            r'''
            SELECT
                keyspace.revision,
                keyspace.key
            FROM
                keyspace
            ''',
        )

    def test_scan(self):
        self.assert_query_regex(
            queries.scan(
                self.tables,
                revision=0,
                key_start=b'x',
                key_end=b'y',
                sorts=(
                    interfaces.Sort(
                        sort_by=interfaces.SortBys.NONE,
                        ascending=True,
                    ),
                    interfaces.Sort(
                        sort_by=interfaces.SortBys.KEY,
                        ascending=True,
                    ),
                    interfaces.Sort(
                        sort_by=interfaces.SortBys.VALUE,
                        ascending=False,
                    ),
                ),
                limit=1,
            ),
            r'''
            SELECT
                keyspace.revision,
                keyspace.key,
                keyspace.value
            FROM
                keyspace
            WHERE
                keyspace.key >= :key_1 AND
                keyspace.key < :key_2
            ORDER BY
                keyspace.key ASC,
                keyspace.value DESC
            LIMIT
                :param_1
            ''',
        )
        self.assert_query_regex(
            queries.scan(
                self.tables,
                revision=1,
                key_start=b'',
                key_end=b'',
                sorts=(
                    interfaces.Sort(
                        sort_by=interfaces.SortBys.NONE,
                        ascending=True,
                    ),
                    interfaces.Sort(
                        sort_by=interfaces.SortBys.VALUE,
                        ascending=False,
                    ),
                ),
                limit=3,
            ),
            r'''
            SELECT
                revisions.revision,
                revisions.key,
                revisions.value
            FROM
                revisions
            JOIN
                \(SELECT
                    max\(revisions.revision\) AS revision,
                    revisions.key AS key
                FROM
                    revisions
                WHERE
                    revisions.revision <= :revision_1
                GROUP BY
                    revisions.key\)
                AS
                    _last_revisions
            ON
                revisions.revision = _last_revisions.revision AND
                revisions.key = _last_revisions.key
            WHERE
                revisions.value IS NOT NULL
            ORDER BY
                revisions.value DESC
            LIMIT
                :param_1
            ''',
        )

    def test_scan_pairs_and_ids(self):
        self.assert_query_regex(
            queries.scan_pairs_and_ids(
                self.tables,
                key_start=b'',
                key_end=b'',
            ),
            r'''
            SELECT
                keyspace.revision,
                keyspace.key,
                keyspace.value,
                keyspace.key_id
            FROM
                keyspace
            ''',
        )
        self.assert_query_regex(
            queries.scan_pairs_and_ids(
                self.tables,
                key_start=b'x',
                key_end=b'y',
            ),
            r'''
            SELECT
                keyspace.revision,
                keyspace.key,
                keyspace.value,
                keyspace.key_id
            FROM
                keyspace
            WHERE
                keyspace.key >= :key_1 AND
                keyspace.key < :key_2
            ''',
        )

    def test_scan_key_ids(self):
        self.assert_query_regex(
            queries.scan_key_ids(
                self.tables,
                key_ids=[1],
            ),
            r'''
            SELECT
                keyspace.revision,
                keyspace.key,
                keyspace.value
            FROM
                keyspace
            WHERE
                keyspace.key_id IN \(\[POSTCOMPILE_key_id_1\]\)
            ''',
        )

    def test_set(self):
        qs = queries.set_(self.tables, revision=0, key=1, value=b'')
        self.assert_query_regex(
            qs[0],
            r'''
            INSERT OR REPLACE INTO
                keyspace
                \(revision, key, value\)
            VALUES
                \(:revision, :key, :value\)
            ''',
        )
        self.assert_query_regex(
            qs[1],
            r'''
            INSERT INTO
                revisions
                \(revision, key, value\)
            VALUES
                \(:revision, :key, :value\)
            ''',
        )

    def test_delete_key_ids(self):
        self.assert_query_regex(
            queries.delete_key_ids(self.tables, key_ids=[1]),
            r'''
            DELETE FROM
                keyspace
            WHERE
                keyspace.key_id IN \(\[POSTCOMPILE_key_id_1\]\)
            ''',
        )

    def test_lease_count(self):
        self.assert_query_regex(
            queries.lease_count(self.tables, lease_start=1, lease_end=2),
            r'''
            SELECT
                count\(\*\) AS count_1
            FROM
                leases
            WHERE
                leases.lease >= :lease_1 AND
                leases.lease < :lease_2
            ''',
        )

    def test_lease_scan(self):
        self.assert_query_regex(
            queries.lease_scan(
                self.tables,
                lease_start=1,
                lease_end=2,
                limit=1,
            ),
            r'''
            SELECT
                _leases.lease,
                _leases.expiration,
                keyspace.key
            FROM
                \(SELECT
                    leases.lease AS lease,
                    leases.expiration AS expiration
                FROM
                    leases
                WHERE
                    leases.lease >= :lease_1 AND
                    leases.lease < :lease_2
                LIMIT
                    :param_1\) AS _leases
            LEFT OUTER JOIN
                leases_key_ids
            ON
                _leases.lease = leases_key_ids.lease
            LEFT OUTER JOIN
                keyspace
            ON
                leases_key_ids.key_id = keyspace.key_id
            ORDER BY
                _leases.lease ASC,
                keyspace.key ASC
            ''',
        )

    def test_lease_grant(self):
        self.assert_query_regex(
            queries.lease_grant(self.tables, lease=1, expiration=0),
            r'''
            INSERT OR REPLACE INTO
                leases
                \(lease, expiration\)
            VALUES
                \(:lease, :expiration\)
            ''',
        )

    def test_lease_associate(self):
        self.assert_query_regex(
            queries.lease_associate(self.tables, lease=1, key_id=1),
            r'''
            INSERT OR REPLACE INTO
                leases_key_ids
                \(lease, key_id\)
            VALUES
                \(:lease, :key_id\)
            ''',
        )

    def test_lease_dissociate(self):
        self.assert_query_regex(
            queries.lease_dissociate(self.tables, lease=1, key_id=1),
            r'''
            DELETE FROM
                leases_key_ids
            WHERE
                leases_key_ids.lease = :lease_1 AND
                leases_key_ids.key_id = :key_id_1
            ''',
        )

    def test_lease_scan_expired(self):
        self.assert_query_regex(
            queries.lease_scan_expired(self.tables, current_time=1),
            r'''
            SELECT
                leases.lease
            FROM
                leases
            WHERE
                leases.expiration < :expiration_1
            ''',
        )

    def test_lease_get_key_ids(self):
        self.assert_query_regex(
            queries.lease_get_key_ids(self.tables, leases=[1]),
            r'''
            SELECT DISTINCT
                leases_key_ids.key_id
            FROM
                leases_key_ids
            WHERE
                leases_key_ids.lease IN \(\[POSTCOMPILE_lease_1\]\)
            ''',
        )

    def test_lease_scan_leases(self):
        self.assert_query_regex(
            queries.lease_scan_leases(self.tables, key_ids=[1]),
            r'''
            SELECT
                leases_key_ids.key_id,
                leases_key_ids.lease
            FROM
                leases_key_ids
            WHERE
                leases_key_ids.key_id IN \(\[POSTCOMPILE_key_id_1\]\)
            ORDER BY
                leases_key_ids.key_id ASC
            ''',
        )

    def test_lease_delete_key_ids(self):
        self.assert_query_regex(
            queries.lease_delete_key_ids(self.tables, key_ids=[1]),
            r'''
            DELETE FROM
                leases_key_ids
            WHERE
                leases_key_ids.key_id IN \(\[POSTCOMPILE_key_id_1\]\)
            ''',
        )

    def test_lease_delete_leases(self):
        qs = queries.lease_delete_leases(self.tables, leases=[1])
        self.assert_query_regex(
            qs[0],
            r'''
            DELETE FROM
                leases
            WHERE
                leases.lease IN \(\[POSTCOMPILE_lease_1\]\)
            ''',
        )
        self.assert_query_regex(
            qs[1],
            r'''
            DELETE FROM
                leases_key_ids
            WHERE
                leases_key_ids.lease IN \(\[POSTCOMPILE_lease_1\]\)
            ''',
        )

    def test_lease_revoke(self):
        qs = queries.lease_revoke(self.tables, lease=1)
        self.assert_query_regex(
            qs[0],
            r'''
            DELETE FROM
                leases
            WHERE
                leases.lease = :lease_1
            ''',
        )
        self.assert_query_regex(
            qs[1],
            r'''
            DELETE FROM
                leases_key_ids
            WHERE
                leases_key_ids.lease = :lease_1
            ''',
        )

    def test_compact(self):
        self.assert_query_regex(
            queries.compact(self.tables, revision=1),
            r'''
            DELETE FROM
                revisions
            WHERE
                revisions.revision < :revision_1
            ''',
        )


if __name__ == '__main__':
    unittest.main()
