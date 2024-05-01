@0x9dbd9910b941379f;

struct Endpoint {
  port @0 :UInt16;
  ipv4 @1 :UInt32;
  # TODO: Add `ipv6` and move `ipv4` and `ipv6` into a union.
}

using Token = UInt64;

struct Request {
  struct Read {
    key @0 :Data;
  }

  struct ReadMetadata {
    key @0 :Data;
  }

  struct Write {
    key @0 :Data;
    metadata @1 :Data;
    size @2 :UInt32;
  }

  union {
    ping @0 :Void;
    read @1 :Read;
    readMetadata @2 :ReadMetadata;
    write @3 :Write;
    cancel @4 :Token;
  }
}

struct Response {
  struct Read {
    metadata @0 :Data;
    size @1 :UInt32;
    endpoint @2 :Endpoint;
    token @3 :Token;
  }

  struct ReadMetadata {
    metadata @0 :Data;
    size @1 :UInt32;
  }

  struct Write {
    endpoint @0 :Endpoint;
    token @1 :Token;
  }

  union {
    ping @0 :Void;
    read @1 :Read;
    readMetadata @2 :ReadMetadata;
    write @3 :Write;
    cancel @4 :Void;
  }
}

struct Error {
  union {
    none @0 :Void;
    unavailable @1 :Void;
    invalidRequest @2 :Void;
    maxKeySizeExceeded @3 :UInt32;
    maxMetadataSizeExceeded @4 :UInt32;
    maxBlobSizeExceeded @5 :UInt32;
  }
}
