__all__ = [
    'DATABASE_PORT',
    'DATABASE_PUBLISHER_PORT',
    # Database interface.
    'DatabaseInterface',
    'DatabaseRequest',
    'DatabaseResponse',
    # Database watcher interface.
    'DatabaseEvent',
    # Type aliases.
    'Expiration',
    'Key',
    'LeaseId',
    'Revision',
    'TransactionId',
    'Value',
    # Data types.
    'KeyValue',
    'Lease',
    'SortBys',
    'Sort',
    # Error types.
    'DatabaseError',
    'InternalError',
    'InvalidRequestError',
    'KeyNotFoundError',
    'LeaseNotFoundError',
    'TransactionNotFoundError',
    'TransactionTimeoutError',
    # Misc.
    'generate_lease_id',
    'generate_transaction_id',
    'next_key',
]

import dataclasses
import enum
import random
import typing

from g1.bases.assertions import ASSERT
from g1.messaging import reqrep

DATABASE_PORT = 2390
DATABASE_PUBLISHER_PORT = 2391

# Type aliases.  Integers are 64-bit.
Revision = int
Key = bytes
Value = bytes
LeaseId = int
Expiration = int  # Unit: seconds.
TransactionId = int


class DatabaseError(Exception):
    """Base error type."""


class InvalidRequestError(DatabaseError):
    """When receiving an invalid request."""


class InternalError(DatabaseError):
    """When a non-DatabaseError exception type is not caught."""


class KeyNotFoundError(DatabaseError):
    """When no key is found for the given ID."""


class LeaseNotFoundError(DatabaseError):
    """When no lease is found for the given ID."""


class TransactionNotFoundError(DatabaseError):
    """When no transaction is found for the given ID."""


class TransactionTimeoutError(DatabaseError):
    """When a transaction has timed out."""


@dataclasses.dataclass(frozen=True)
class KeyOnly:
    revision: Revision
    key: Key

    def __post_init__(self):
        ASSERT.greater(self.revision, 0)
        ASSERT.true(self.key)


@dataclasses.dataclass(frozen=True)
class KeyValue:
    """Represent a key-value pair.

    * The revision field is last revision at which this pair was
      modified.  Note that this is not the revision of the current
      keyspace.

    * The key field is never an empty string since we do not allow such
      case for now.
    """
    revision: Revision
    key: Key
    value: Value

    def __post_init__(self):
        ASSERT.greater(self.revision, 0)
        ASSERT.true(self.key)


@enum.unique
class SortBys(enum.Enum):
    """Instruct how scan operations sort their results.

    Note that REVISION means the last modified revision of a key, not
    the revision of the keyspace we are scanning.
    """
    NONE = 0
    REVISION = 1
    KEY = 2
    VALUE = 3


@dataclasses.dataclass(frozen=True)
class Sort:
    sort_by: SortBys
    ascending: bool


@dataclasses.dataclass(frozen=True)
class Lease:
    lease: LeaseId
    expiration: Expiration
    keys: typing.List[Key]

    def __post_init__(self):
        ASSERT.greater(self.lease, 0)
        ASSERT.greater_or_equal(self.expiration, 0)


@reqrep.raising(
    InvalidRequestError,
    InternalError,
    TransactionNotFoundError,
    TransactionTimeoutError,
)
class DatabaseInterface:
    """Database interface.

    This is modeled after etcd with a few differences:

    * A transaction covers multiple operations (rather than a special
      transaction request bundle together operations).
    * All write operations are idempotent.
    * Lease operations do not increment revision.

    NOTE: Although we model the interface after etcd, and offer more in
    certain aspects, our storage implementation is based on SQLite.  So
    in terms of actual supported concurrent operations and performance,
    our server is mostly just a toy compared to etcd.

    Common arguments:

    * revision:
      Scan the keyspace at this revision.  The special value 0 means the
      current revision.

    * limit:
      Return no more results than the given number.  The special value 0
      means returning all results.

    * transaction:
      Execute this request in the given transaction.  The special value
      0 means no transaction.  When it is not 0, methods might raise
      TransactionNotFoundError or TransactionTimeoutError.
    """

    __module__ = 'g1.operations.databases'

    #
    # Key-value operations.
    #

    def get_revision(self, *, transaction: TransactionId = 0) -> Revision:
        """Return the revision of the current keyspace."""
        raise NotImplementedError

    def get(
        self,
        *,
        key: Key,
        revision: Revision = 0,
        transaction: TransactionId = 0,
    ) -> typing.Optional[KeyValue]:
        """Get the pair by the given key, at the given revision.

        * key:
          Get the pair by the given key.  This cannot be empty.
        """
        raise NotImplementedError

    def count(
        self,
        *,
        revision: Revision = 0,
        key_start: Key = b'',
        key_end: Key = b'',
        transaction: TransactionId = 0,
    ) -> int:
        """Scan key spaces but only return the count of the results.

        Check scan for descriptions of arguments.
        """
        raise NotImplementedError

    def scan_keys(
        self,
        *,
        revision: Revision = 0,
        key_start: Key = b'',
        key_end: Key = b'',
        sorts: typing.List[Sort] = (),
        limit: int = 0,
        transaction: TransactionId = 0,
    ) -> typing.List[KeyOnly]:
        """Scan key spaces but only return keys of the results.

        Check scan for descriptions of arguments.
        """
        raise NotImplementedError

    def scan(
        self,
        *,
        revision: Revision = 0,
        key_start: Key = b'',
        key_end: Key = b'',
        sorts: typing.List[Sort] = (),
        limit: int = 0,
        transaction: TransactionId = 0,
    ) -> typing.List[KeyValue]:
        """Scan key spaces.

        * key_start, key_end:
          Scan keys of the given range.  An empty byte string means that
          end of the range is unbounded.  Default is to scan the entire
          key space.

        * sorts:
          Sort results by the given conditions.  Default is to sort
          results by an implementation defined order.
        """
        raise NotImplementedError

    def set(
        self,
        *,
        key: Key,
        value: Value,
        transaction: TransactionId = 0,
    ) -> typing.Optional[KeyValue]:
        """Set a key-value pair.

        This increments the revision by 1, and returns the key-value
        pair prior to the update.

        This is idempotent in the sense that if the value is the same as
        the current value, the revision is not incremented.

        * key:
          Set to the pair by the given key.  This cannot be empty.

        * value:
          Set the value of the pair to the given value.  This cannot be
          empty.
        """
        raise NotImplementedError

    def delete(
        self,
        *,
        key_start: Key = b'',
        key_end: Key = b'',
        transaction: TransactionId = 0,
    ) -> typing.List[KeyValue]:
        """Delete pairs of the given key range.

        This increments the revision by 1, and returns the key-value
        pairs prior to the deletion.

        This is idempotent in the sense that if no key is deleted, the
        revision is not incremented.

        Check scan for descriptions of arguments.
        """
        raise NotImplementedError

    #
    # Leases.
    #

    def lease_get(
        self,
        *,
        lease: LeaseId,
        transaction: TransactionId = 0,
    ) -> typing.Optional[Lease]:
        """Get lease.

        * lease:
          Lease ID to get for.
        """
        raise NotImplementedError

    def lease_count(
        self,
        *,
        lease_start: LeaseId = 0,
        lease_end: LeaseId = 0,
        transaction: TransactionId = 0,
    ) -> int:
        """Count leases.

        Check lease_scan for descriptions of arguments.
        """
        raise NotImplementedError

    def lease_scan(
        self,
        *,
        lease_start: LeaseId = 0,
        lease_end: LeaseId = 0,
        limit: int = 0,
        transaction: TransactionId = 0,
    ) -> typing.List[Lease]:
        """Scan leases.

        * lease_start, lease_end:
          Scan leases of the given range.  The special value 0 means
          that end of the range is unbounded.  Default is to scan all
          leases.
        """
        raise NotImplementedError

    def lease_grant(
        self,
        *,
        lease: LeaseId,
        expiration: Expiration,
        transaction: TransactionId = 0,
    ) -> typing.Optional[Lease]:
        """Grant a new lease or extend the expiration time.

        This returns the lease object prior to the call.

        This is idempotent in the sense that if the lease exists, this
        updates the expiration time.

        * lease:
          The new lease ID.  This cannot be empty.

        * expiration:
          The expiration time of the lease.
        """
        raise NotImplementedError

    @reqrep.raising(
        KeyNotFoundError,
        LeaseNotFoundError,
    )
    def lease_associate(
        self,
        *,
        lease: LeaseId,
        key: Key,
        transaction: TransactionId = 0,
    ) -> Lease:
        """Associate a lease with a key.

        This returns the lease object prior to the call.

        This is idempotent in the sense that if the lease is already
        associated with the key, this is a no-op.

        * lease:
          Lease ID in the association.  It cannot be empty.  This raises
          LeaseNotFoundError if lease does not exist.

        * key:
          Key in the association.  It cannot be empty.  This raises
          KeyNotFoundError if key does not exist.
        """
        raise NotImplementedError

    @reqrep.raising(
        KeyNotFoundError,
        LeaseNotFoundError,
    )
    def lease_dissociate(
        self,
        *,
        lease: LeaseId,
        key: Key,
        transaction: TransactionId = 0,
    ) -> Lease:
        """Dissociate a lease from a key.

        This returns the lease object prior to the call.

        This is idempotent in the sense that if the lease is not
        associated with the key, this is a no-op.

        Check lease_associate for descriptions of arguments.
        """
        raise NotImplementedError

    def lease_revoke(
        self,
        *,
        lease: LeaseId,
        transaction: TransactionId = 0,
    ) -> typing.Optional[Lease]:
        """Revoke the given lease.

        This is idempotent in the sense that if the lease does not
        exist, it is a no-op.

        * lease:
          The lease ID, which cannot be empty.
        """
        raise NotImplementedError

    #
    # Transactions.
    #

    def begin(self, *, transaction: TransactionId):
        """Begin a transaction.

        This raises TransactionTimeoutError if it cannot begin a
        transaction (probably because other transactions are still in
        progress).

        This is idempotent in the sense that if the transaction has
        begun already, this is a no-op.

        NOTE: Strictly speaking, given this interface design, there is
        a chance that two clients begin their transactions with the same
        transaction ID.  Nevertheless, since transaction IDs are 64-bit
        integers, the chance of collision among randomly-generated IDs
        is very, very low in practical terms.
        """
        raise NotImplementedError

    def rollback(self, *, transaction: TransactionId):
        """Roll back a transaction.

        This is idempotent in the sense that if the transaction was
        already rolled back, this is a no-op.
        """
        raise NotImplementedError

    def commit(self, *, transaction: TransactionId):
        """Commit a transaction.

        This is idempotent in the sense that if the transaction was
        already committed, this is a no-op.
        """
        raise NotImplementedError

    #
    # Maintenance.
    #

    def compact(self, *, revision: Revision):
        """Remove key spaces before the given revision.

        This does not remove the current key space even if the given
        revision is greater than the current revision.
        """
        raise NotImplementedError


DatabaseRequest, DatabaseResponse = reqrep.generate_interface_types(
    DatabaseInterface, 'Database'
)


@dataclasses.dataclass(frozen=True)
class DatabaseEvent:
    """Event of a key space change."""

    __module__ = 'g1.operations.databases'

    # Although these fields are None-able, we strip off typing.Optional
    # annotation from them because our capnp converter does not support
    # typing.Union nor typing.Optional.
    previous: KeyValue
    current: KeyValue

    def __post_init__(self):
        ASSERT.any((self.previous is not None, self.current is not None))
        if self.previous is not None and self.current is not None:
            ASSERT.less(self.previous.revision, self.current.revision)
            ASSERT.equal(self.previous.key, self.current.key)

    # It is possible that both values are None (after the key spaces
    # were compacted).

    def is_creation(self):
        # NOTE: We could have a "false" creation if the key spaces were
        # compacted.  For now we do not handle this case.
        return self.previous is None and self.current is not None

    def is_update(self):
        return self.previous is not None and self.current is not None

    def is_deletion(self):
        return self.current is None


def generate_lease_id():
    return random.randrange(1, 1 << 64)


def generate_transaction_id():
    return random.randrange(1, 1 << 64)


def next_key(key):
    ASSERT.true(key)
    bs = []
    carry = 1
    for b in reversed(key):
        b += carry
        if b > 0xff:
            bs.append(0)
        else:
            bs.append(b)
            carry = 0
    if carry:
        bs.append(1)
    bs.reverse()
    return bytes(bs)
