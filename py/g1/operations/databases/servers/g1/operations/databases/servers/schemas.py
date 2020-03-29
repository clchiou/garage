__all__ = [
    'make_tables',
]

from sqlalchemy import (
    Column,
    Table,
    # Column types.
    BigInteger,
    Integer,
    LargeBinary,
)

from g1.bases import collections as g1_collections

# Type aliases.
Revision = BigInteger
Key = LargeBinary
Value = LargeBinary
Lease = BigInteger
Expiration = BigInteger


def make_tables(metadata):
    return g1_collections.Namespace(
        # Store the current revision of the keyspace.  This is not
        # compacted and is monotonically increasing.  This table should
        # have at most one row at any given time.
        current_revision=Table(
            'current_revision',
            metadata,
            Column('revision', Revision, primary_key=True),
        ),
        # Store the current keyspace, which is denormalized from the
        # revisions table so that the current keyspace is never
        # compacted.  Also this table supports faster lookup in common
        # use cases.
        keyspace=Table(
            'keyspace',
            metadata,
            Column('key_id', Integer, primary_key=True),
            Column('revision', Revision, nullable=False),
            Column('key', Key, nullable=False, index=True, unique=True),
            Column('value', Value, nullable=False),
        ),
        # Store revisions (create/update/delete) of pairs.  Note that
        # this they are not revisions of keyspaces and they may get
        # compacted; so the history may be incomplete.
        revisions=Table(
            'revisions',
            metadata,
            Column('revision', Revision, primary_key=True),
            Column('key', Key, primary_key=True),
            Column('value', Value),
        ),
        leases=Table(
            'leases',
            metadata,
            Column('lease', Lease, primary_key=True),
            Column('expiration', Expiration, nullable=False, index=True),
        ),
        leases_key_ids=Table(
            'leases_key_ids',
            metadata,
            Column('lease', Revision, primary_key=True),
            Column('key_id', Integer, primary_key=True),
        ),
    )
