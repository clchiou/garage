@0x9787da802dff9713;

using Timestamp = UInt64;

struct Request {
  #
  # Client-Server Protocol
  #

  struct Get {
    key @0 :Data;
  }

  struct Set {
    key @0 :Data;
    value @1 :Data;
    expireAt @2 :Timestamp;
  }

  struct Update {
    key @0 :Data;
    value :union {
      dont @1 :Void;
      set @2 :Data;
    }
    expireAt :union {
      dont @3 :Void;
      set @4 :Timestamp;
    }
  }

  struct Remove {
    key @0 :Data;
  }

  #
  # Peer Protocol
  #
  # TODO: I am not sure if this is a good idea, but for now, we are not splitting the peer protocol
  # into a standalone struct.

  # Similar to `Get`, except that it does not update the cache entry's recency.
  struct Pull {
    key @0 :Data;
  }

  # Similar to `Set`, except that the receiving peer may decline it if the peer has the entry.
  struct Push {
    key @0 :Data;
    value @1 :Data;
    expireAt @2 :Timestamp;
  }

  union {
    ping @0 :Void;

    get @1 :Get;
    set @2 :Set;
    update @3 :Update;
    remove @4 :Remove;

    pull @5 :Pull;
    push @6 :Push;
  }
}

struct Response {
  value @0 :Data;
  expireAt @1 :Timestamp;
}

struct Error {
  union {
    server @0 :Void;

    unavailable @1 :Void;

    invalidRequest @2 :Void;
    # More refined invalid request errors.
    maxKeySizeExceeded @3 :UInt32;
    maxValueSizeExceeded @4 :UInt32;
  }
}
