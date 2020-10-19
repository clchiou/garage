"""Low-level database operations."""

__all__ = [
    # Key-value operations.
    'count',
    'delete',
    'get',
    'get_revision',
    'increment_revision',
    'scan',
    'scan_keys',
    'set_',
    # Leases.
    'lease_count',
    'lease_expire',
    'lease_get',
    'lease_scan',
    'lease_scan_expirations',
    'lease_grant',
    'lease_associate',
    'lease_dissociate',
    'lease_revoke',
    # Maintenance.
    'compact',
]

# We use **kwargs quite often in this module because most functions are
# merely passing through named arguments to the queries module, but
# pylint is not too happy about this; so let's disable this warning at
# module-level.
#
# pylint: disable=missing-kwoa

import contextlib
import itertools

from g1.bases.assertions import ASSERT
from g1.operations.databases.bases import interfaces

from . import queries


def get_revision(conn, tables):
    """Return the current revision.

    This raises when the table has more than one row.
    """
    with _executing(conn, queries.get_revision(tables)) as result:
        return _scalar_or_none(result) or 0


def increment_revision(conn, tables, *, revision):
    """Set the current revision to one plus the given revision.

    This raises when the current revision does not equal to the given
    revision.

    This is idempotent in the sense that if the current revision was
    set to "plus one" already, this is a no-op.
    """
    with _executing(
        conn,
        queries.increment_revision(tables, revision=revision),
    ) as result:
        if result.rowcount == 0:
            ASSERT.equal(get_revision(conn, tables), revision + 1)
        else:
            ASSERT.equal(result.rowcount, 1)


def get(conn, tables, **kwargs):
    with _executing(conn, queries.get(tables, **kwargs)) as result:
        row = result.first()
        return None if row is None or row[2] is None else _make_pair(row)


def _get_key_id(conn, tables, **kwargs):
    with _executing(conn, queries.get_key_id(tables, **kwargs)) as result:
        return result.scalar()


def count(conn, tables, **kwargs):
    with _executing(conn, queries.count(tables, **kwargs)) as result:
        return ASSERT.not_none(result.scalar())


def scan_keys(conn, tables, **kwargs):
    with _executing(conn, queries.scan_keys(tables, **kwargs)) as result:
        return [
            interfaces.KeyOnly(revision=row[0], key=row[1]) for row in result
        ]


def scan(conn, tables, **kwargs):
    with _executing(conn, queries.scan(tables, **kwargs)) as result:
        return list(map(_make_pair, result))


def set_(conn, tables, *, key, value, tx_revision=None):
    ASSERT.true(key)
    prior = get(conn, tables, revision=0, key=key)
    if prior is not None and prior.value == value:
        return prior  # `set_` is idempotent.
    revision = _handle_tx_revision(conn, tables, tx_revision)
    for query in queries.set_(tables, revision=revision, key=key, value=value):
        _execute(conn, query)
    return prior


def delete(conn, tables, *, tx_revision=None, **kwargs):
    prior, key_ids = _scan_pairs_and_ids(conn, tables, **kwargs)
    if not prior:
        return prior  # `delete` is idempotent.
    revision = _handle_tx_revision(conn, tables, tx_revision)
    _execute(conn, queries.delete_key_ids(tables, key_ids=key_ids))
    _record_deletions(conn, tables, revision, (pair.key for pair in prior))
    _execute(conn, queries.lease_delete_key_ids(tables, key_ids=key_ids))
    return prior


def _scan_pairs_and_ids(conn, tables, **kwargs):
    pairs = []
    ids = []
    with _executing(
        conn,
        queries.scan_pairs_and_ids(tables, **kwargs),
    ) as result:
        for row in result:
            pairs.append(_make_pair(row))
            ids.append(row[-1])
    return pairs, ids


def lease_get(conn, tables, *, lease):
    ASSERT.greater(lease, 0)
    leases = lease_scan(
        conn, tables, lease_start=lease, lease_end=lease + 1, limit=1
    )
    return leases[0] if leases else None


def lease_count(conn, tables, **kwargs):
    with _executing(conn, queries.lease_count(tables, **kwargs)) as result:
        return ASSERT.not_none(result.scalar())


def lease_scan(conn, tables, **kwargs):
    with _executing(conn, queries.lease_scan(tables, **kwargs)) as result:
        leases = []
        for _, group in itertools.groupby(result, key=lambda row: row[0]):
            first = next(group)
            leases.append(
                interfaces.Lease(
                    lease=first[0],
                    expiration=first[1],
                    keys=tuple(
                        row[2]
                        for row in itertools.chain((first, ), group)
                        if row[2] is not None
                    ),
                )
            )
        return leases


def lease_scan_expirations(conn, tables):
    with _executing(conn, queries.lease_scan_expirations(tables)) as result:
        return [row[0] for row in result]


def lease_grant(conn, tables, **kwargs):
    prior = lease_get(conn, tables, lease=kwargs['lease'])
    _execute(conn, queries.lease_grant(tables, **kwargs))
    return prior


def lease_associate(conn, tables, *, lease, key):
    ASSERT.greater(lease, 0)
    ASSERT.true(key)
    prior = lease_get(conn, tables, lease=lease)
    if prior is None:
        raise interfaces.LeaseNotFoundError
    key_id = _get_key_id(conn, tables, key=key)
    if key_id is None:
        raise interfaces.KeyNotFoundError
    _execute(conn, queries.lease_associate(tables, lease=lease, key_id=key_id))
    return prior


def lease_dissociate(conn, tables, *, lease, key):
    ASSERT.greater(lease, 0)
    ASSERT.true(key)
    prior = lease_get(conn, tables, lease=lease)
    if prior is None:
        raise interfaces.LeaseNotFoundError
    key_id = _get_key_id(conn, tables, key=key)
    if key_id is None:
        raise interfaces.KeyNotFoundError
    _execute(
        conn, queries.lease_dissociate(tables, lease=lease, key_id=key_id)
    )
    return prior


def lease_expire(conn, tables, *, tx_revision=None, **kwargs):
    expired = _lease_scan_expired(conn, tables, **kwargs)
    if not expired:
        return []
    key_ids = _lease_get_key_ids(conn, tables, leases=expired)
    if key_ids:
        # Exclude key ids that are associated with non-expiring leases.
        for key_id, leases in _lease_scan_leases(
            conn,
            tables,
            key_ids=key_ids,
        ):
            if not leases.issubset(expired):
                key_ids.remove(key_id)
    for query in queries.lease_delete_leases(tables, leases=expired):
        _execute(conn, query)
    if key_ids:
        with _executing(
            conn,
            queries.scan_key_ids(tables, key_ids=key_ids),
        ) as result:
            prior = [_make_pair(row) for row in result]
        revision = _handle_tx_revision(conn, tables, tx_revision)
        _execute(conn, queries.delete_key_ids(tables, key_ids=key_ids))
        _record_deletions(conn, tables, revision, (pair.key for pair in prior))
    else:
        prior = []
    return prior


def _lease_scan_expired(conn, tables, *, current_time):
    with _executing(
        conn,
        queries.lease_scan_expired(tables, current_time=current_time),
    ) as result:
        return set(row[0] for row in result)


def _lease_get_key_ids(conn, tables, *, leases):
    with _executing(
        conn,
        queries.lease_get_key_ids(tables, leases=leases),
    ) as result:
        return set(row[0] for row in result)


def _lease_scan_leases(conn, tables, *, key_ids):
    with _executing(
        conn,
        queries.lease_scan_leases(tables, key_ids=key_ids),
    ) as result:
        return [(key_id, set(row[1] for row in group)) for key_id, group in
                itertools.groupby(result, key=lambda row: row[0])]


def lease_revoke(conn, tables, **kwargs):
    prior = lease_get(conn, tables, **kwargs)
    if prior is None:
        return None
    for query in queries.lease_revoke(tables, **kwargs):
        _execute(conn, query)
    return prior


def compact(conn, tables, **kwargs):
    _execute(conn, queries.compact(tables, **kwargs))


def _handle_tx_revision(conn, tables, tx_revision):
    if tx_revision is not None:
        return tx_revision
    revision = get_revision(conn, tables)
    increment_revision(conn, tables, revision=revision)
    return revision


def _record_deletions(conn, tables, revision, keys):
    _execute(
        conn,
        tables.revisions.insert(),
        [{
            'revision': revision + 1,
            'key': key,
            'value': None
        } for key in keys],
    )


@contextlib.contextmanager
def _executing(conn, stmt):
    result = conn.execute(stmt)
    try:
        yield result
    finally:
        result.close()


def _execute(conn, stmt, *args):
    conn.execute(stmt, *args).close()


def _scalar_or_none(result):
    row = result.fetchone()
    if row is None:
        return None
    ASSERT.none(result.fetchone())
    return row[0]


def _make_pair(row):
    return interfaces.KeyValue(revision=row[0], key=row[1], value=row[2])
