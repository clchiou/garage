@0xb3dc65c741d83c8e;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("g1::operations::databases");

using Java = import "/capnp/java.capnp";
$Java.package("g1.operations");
$Java.outerClassname("Databases");

using Revision = UInt64;
using Key = Data;
using Value = Data;
using LeaseId = UInt64;
using Expiration = UInt64;  # Unit: seconds.
using TransactionId = UInt64;

struct InternalError {
}

struct InvalidRequestError {
}

struct KeyNotFoundError {
}

struct LeaseNotFoundError {
}

struct TransactionNotFoundError {
}

struct TransactionTimeoutError {
}

struct KeyOnly {
  revision @0 :Revision;
  key @1 :Key;
}

struct KeyValue {
  revision @0 :Revision;
  key @1 :Key;
  value @2 :Value;
}

enum SortBys {
  none @0;
  revision @1;
  key @2;
  value @3;
}

struct Sort {
  sortBy @0 :SortBys;
  ascending @1 :Bool;
}

struct Lease {
  lease @0 :LeaseId;
  expiration @1 :Expiration;
  keys @2 :List(Key);
}

struct DatabaseRequest {
  struct Args {
    struct GetRevision {
      transaction @0 :TransactionId;
    }
    struct Get {
      transaction @0 :TransactionId;
      revision @1 :Revision;
      key @2 :Key;
    }
    struct Count {
      transaction @0 :TransactionId;
      revision @1 :Revision;
      keyStart @2 :Key;
      keyEnd @3 :Key;
    }
    struct ScanKeys {
      transaction @0 :TransactionId;
      revision @1 :Revision;
      keyStart @2 :Key;
      keyEnd @3 :Key;
      sorts @4 :List(Sort);
      limit @5 :Int32;
    }
    struct Scan {
      transaction @0 :TransactionId;
      revision @1 :Revision;
      keyStart @2 :Key;
      keyEnd @3 :Key;
      sorts @4 :List(Sort);
      limit @5 :Int32;
    }
    struct Set {
      transaction @0 :TransactionId;
      key @1 :Key;
      value @2 :Value;
    }
    struct Delete {
      transaction @0 :TransactionId;
      keyStart @1 :Key;
      keyEnd @2 :Key;
    }
    struct LeaseGet {
      transaction @0 :TransactionId;
      lease @1 :LeaseId;
    }
    struct LeaseCount {
      transaction @0 :TransactionId;
      leaseStart @1 :LeaseId;
      leaseEnd @2 :LeaseId;
    }
    struct LeaseScan {
      transaction @0 :TransactionId;
      leaseStart @1 :LeaseId;
      leaseEnd @2 :LeaseId;
      limit @3 :Int32;
    }
    struct LeaseGrant {
      transaction @0 :TransactionId;
      lease @1 :LeaseId;
      expiration @2 :Expiration;
    }
    struct LeaseAssociate {
      transaction @0 :TransactionId;
      lease @1 :LeaseId;
      key @2 :Key;
    }
    struct LeaseDissociate {
      transaction @0 :TransactionId;
      lease @1 :LeaseId;
      key @2 :Key;
    }
    struct LeaseRevoke {
      transaction @0 :TransactionId;
      lease @1 :LeaseId;
    }
    struct Begin {
      transaction @0 :TransactionId;
    }
    struct Rollback {
      transaction @0 :TransactionId;
    }
    struct Commit {
      transaction @0 :TransactionId;
    }
    struct Compact {
      revision @0 :Revision;
    }
    union {
      getRevision @0 :GetRevision;
      get @1 :Get;
      count @2 :Count;
      scanKeys @3 :ScanKeys;
      scan @4 :Scan;
      set @5 :Set;
      delete @6 :Delete;
      leaseGet @7 :LeaseGet;
      leaseCount @8 :LeaseCount;
      leaseScan @9 :LeaseScan;
      leaseGrant @10 :LeaseGrant;
      leaseAssociate @11 :LeaseAssociate;
      leaseDissociate @12 :LeaseDissociate;
      leaseRevoke @13 :LeaseRevoke;
      begin @14 :Begin;
      rollback @15 :Rollback;
      commit @16 :Commit;
      compact @17 :Compact;
    }
  }
  args @0 :Args;
}

struct DatabaseResponse {
  struct Result {
    union {
      getRevision @0 :Revision;
      get @1 :KeyValue;
      count @2 :Int32;
      scanKeys @3 :List(KeyOnly);
      scan @4 :List(KeyValue);
      set @5 :KeyValue;
      delete @6 :List(KeyValue);
      leaseGet @7 :Lease;
      leaseCount @8 :Int32;
      leaseScan @9 :List(Lease);
      leaseGrant @10 :Lease;
      leaseAssociate @11 :Lease;
      leaseDissociate @12 :Lease;
      leaseRevoke @13 :Lease;
      begin @14 :Void;
      rollback @15 :Void;
      commit @16 :Void;
      compact @17 :Void;
    }
  }
  struct Error {
    union {
      internalError @0 :InternalError;
      invalidRequestError @1 :InvalidRequestError;
      keyNotFoundError @2 :KeyNotFoundError;
      leaseNotFoundError @3 :LeaseNotFoundError;
      transactionNotFoundError @4 :TransactionNotFoundError;
      transactionTimeoutError @5 :TransactionTimeoutError;
    }
  }
  union {
    result @0 :Result;
    error @1 :Error;
  }
}

struct DatabaseEvent {
  previous @0 :KeyValue;
  current @1 :KeyValue;
}
