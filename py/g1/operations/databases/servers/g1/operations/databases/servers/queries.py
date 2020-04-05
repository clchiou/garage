"""Make SQL queries."""

__all__ = [
    # Key-value operations.
    'count',
    'delete_key_ids',
    'get',
    'get_key_id',
    'get_revision',
    'increment_revision',
    'scan',
    'scan_keys',
    'scan_pairs_and_ids',
    'set',
    # Leases.
    'lease_associate',
    'lease_count',
    'lease_delete_expired',
    'lease_delete_key_ids',
    'lease_dissociate',
    'lease_grant',
    'lease_revoke',
    'lease_scan',
    'lease_scan_expired',
    # Maintenance.
    'compact',
]

from sqlalchemy import (
    func,
    join,
    select,
)

from g1.bases.assertions import ASSERT
from g1.databases import sqlite
from g1.operations.databases.bases import interfaces


def get_revision(tables):
    return select([tables.current_revision.c.revision])


def increment_revision(tables, *, revision):
    ASSERT.greater_or_equal(revision, 0)
    if revision == 0:
        return sqlite.upsert(tables.current_revision).values(revision=1)
    return (
        tables.current_revision.update()\
        .where(tables.current_revision.c.revision == revision)
        .values(revision=revision + 1)
    )


def get_key_id(tables, *, key):
    """Query the key ID from the current keyspace."""
    ASSERT.true(key)
    table = tables.keyspace
    return select([table.c.key_id]).where(table.c.key == key)


def get(tables, *, key, revision=0):
    ASSERT.true(key)
    if revision == 0:
        table = tables.keyspace
        return (
            select([table.c.revision, table.c.key, table.c.value])\
            .where(table.c.key == key)
        )
    else:
        table = tables.revisions
        return (
            select([table.c.revision, table.c.key, table.c.value])\
            .where(table.c.revision <= revision)
            .where(table.c.key == key)
            .order_by(table.c.revision.desc())
        )


def count(tables, **kwargs):
    return _scan(
        tables,
        lambda table: [func.count()],
        sorts=(),
        limit=0,
        **kwargs,
    )


def scan_keys(tables, **kwargs):
    return _scan(
        tables,
        lambda table: [table.c.revision, table.c.key],
        **kwargs,
    )


def scan(tables, **kwargs):
    return _scan(
        tables,
        lambda table: [table.c.revision, table.c.key, table.c.value],
        **kwargs,
    )


def scan_pairs_and_ids(tables, **kwargs):
    return _scan(
        tables,
        lambda table: [
            table.c.revision,
            table.c.key,
            table.c.value,
            table.c.key_id,
            # Put key_id at last so that the column order is compatible
            # with scan.
        ],
        revision=0,
        sorts=(),
        limit=0,
        **kwargs,
    )


def _scan(
    tables,
    make_columns,
    *,
    revision=0,
    key_start=b'',
    key_end=b'',
    sorts=(),
    limit=0,
):
    ASSERT.greater_or_equal(revision, 0)
    ASSERT.greater_or_equal(limit, 0)
    query, table = _make_keyspace_table(tables, revision)
    query = select(make_columns(table)).select_from(query)
    query = _add_range(query, table.c.key, key_start, key_end)
    if revision != 0:
        query = query.where(table.c.value != None)  # pylint: disable=singleton-comparison
    for sort_ in sorts:
        query = _add_sort(table, query, sort_)
    query = _add_limit(query, limit)
    return query


def _make_keyspace_table(tables, revision):
    if revision == 0:
        return tables.keyspace, tables.keyspace
    table = tables.revisions
    query = (
        select([
            func.max(table.c.revision).label('revision'),
            table.c.key,
        ])\
        .where(table.c.revision <= revision)
        .group_by(table.c.key)
        .alias('_last_revisions')
    )
    query = join(
        table,
        query,
        (table.c.revision == query.c.revision) & (table.c.key == query.c.key),
    )
    return query, table


def set(tables, *, revision, key, value):  # pylint: disable=redefined-builtin
    ASSERT.greater_or_equal(revision, 0)
    ASSERT.true(key)
    ivs = {'revision': revision + 1, 'key': key, 'value': value}
    return [
        sqlite.upsert(tables.keyspace).values(**ivs),
        tables.revisions.insert().values(**ivs),
    ]


def delete_key_ids(tables, *, key_ids):
    ASSERT.not_empty(key_ids)
    table = tables.keyspace
    return table.delete().where(table.c.key_id.in_(key_ids))


def lease_count(tables, *, lease_start=0, lease_end=0):
    ASSERT.greater_or_equal(lease_start, 0)
    ASSERT.greater_or_equal(lease_end, 0)
    query = select([func.count()]).select_from(tables.leases)
    query = _add_range(query, tables.leases.c.lease, lease_start, lease_end)
    return query


def lease_scan(tables, *, lease_start=0, lease_end=0, limit=0):
    ASSERT.greater_or_equal(lease_start, 0)
    ASSERT.greater_or_equal(lease_end, 0)
    ASSERT.greater_or_equal(limit, 0)
    query = select([
        tables.leases.c.lease,
        tables.leases.c.expiration,
    ])
    query = _add_range(query, tables.leases.c.lease, lease_start, lease_end)
    query = _add_limit(query, limit)
    query = query.alias('_leases')
    joined = join(
        query,
        tables.leases_key_ids,
        query.c.lease == tables.leases_key_ids.c.lease,
        isouter=True,
    )
    joined = join(
        joined,
        tables.keyspace,
        tables.leases_key_ids.c.key_id == tables.keyspace.c.key_id,
        isouter=True,
    )
    return (
        select([
            query.c.lease,
            query.c.expiration,
            tables.keyspace.c.key,
        ])\
        .select_from(joined)
        # Order by lease ID so that we can itertools.groupby on it.
        .order_by(query.c.lease.asc())
        # Order by key so that key order is deterministic.
        .order_by(tables.keyspace.c.key.asc())
    )


def lease_grant(tables, *, lease, expiration):
    ASSERT.greater(lease, 0)
    ASSERT.greater_or_equal(expiration, 0)
    return sqlite.upsert(tables.leases).values(
        lease=lease,
        expiration=expiration,
    )


def lease_associate(tables, *, lease, key_id):
    ASSERT.greater(lease, 0)
    return sqlite.upsert(tables.leases_key_ids).values(
        lease=lease,
        key_id=key_id,
    )


def lease_dissociate(tables, *, lease, key_id):
    ASSERT.greater(lease, 0)
    return (
        tables.leases_key_ids.delete()\
        .where(tables.leases_key_ids.c.lease == lease)
        .where(tables.leases_key_ids.c.key_id == key_id)
    )


def lease_scan_expired(tables, *, current_time):
    ASSERT.greater_or_equal(current_time, 0)
    query = (
        select([tables.leases.c.lease])\
        .where(tables.leases.c.expiration < current_time)
        .alias('_expired')
    )
    joined = join(
        query,
        tables.leases_key_ids,
        query.c.lease == tables.leases_key_ids.c.lease,
    )
    joined = join(
        joined,
        tables.keyspace,
        tables.leases_key_ids.c.key_id == tables.keyspace.c.key_id,
    )
    return select(
        [
            tables.keyspace.c.revision,
            tables.keyspace.c.key,
            tables.keyspace.c.value,
            tables.keyspace.c.key_id,
            # Put key_id at last so that the column order is compatible
            # with _make_pair.
        ],
        distinct=True,
    ).select_from(joined)


def lease_delete_expired(tables, *, current_time):
    ASSERT.greater_or_equal(current_time, 0)
    return (
        tables.leases.delete()\
        .where(tables.leases.c.expiration < current_time)
    )


def lease_delete_key_ids(tables, *, key_ids):
    ASSERT.not_empty(key_ids)
    table = tables.leases_key_ids
    return table.delete().where(table.c.key_id.in_(key_ids))


def lease_revoke(tables, *, lease):
    ASSERT.greater(lease, 0)
    return [
        table.delete().where(table.c.lease == lease)
        for table in (tables.leases, tables.leases_key_ids)
    ]


def compact(tables, *, revision):
    ASSERT.greater_or_equal(revision, 0)
    table = tables.revisions
    return table.delete().where(table.c.revision < revision)


def _add_range(query, column, start, end):
    if start:
        query = query.where(column >= start)
    if end:
        query = query.where(column < end)
    return query


def _add_sort(table, query, sort_):
    if sort_.sort_by is interfaces.SortBys.NONE:
        return query
    if sort_.sort_by is interfaces.SortBys.REVISION:
        column = table.c.revision
    elif sort_.sort_by is interfaces.SortBys.KEY:
        column = table.c.key
    elif sort_.sort_by is interfaces.SortBys.VALUE:
        # How are NULL values ordered?
        column = table.c.value
    else:
        return ASSERT.unreachable('unknown sort by: {}', sort_)
    if sort_.ascending:
        query = query.order_by(column.asc())
    else:
        query = query.order_by(column.desc())
    return query


def _add_limit(query, limit):
    if limit > 0:
        query = query.limit(limit)
    return query
