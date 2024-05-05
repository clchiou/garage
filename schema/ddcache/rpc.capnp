@0x9dbd9910b941379f;

using Timestamp = UInt64;

using Token = UInt64;

struct Endpoint {
  port @0 :UInt16;
  ipv4 @1 :UInt32;
  # TODO: Add `ipv6` and move `ipv4` and `ipv6` into a union.
}

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
    expireAt @3 :Timestamp;
  }

  struct WriteMetadata {
    key @0 :Data;
    metadata :union {
      dont @1 :Void;
      write @2 :Data;
    }
    expireAt :union {
      dont @3 :Void;
      write @4 :Timestamp;
    }
  }

  struct Remove {
    key @0 :Data;
  }

  union {
    cancel @0 :Token;
    read @1 :Read;
    readMetadata @2 :ReadMetadata;
    write @3 :Write;
    writeMetadata @4 :WriteMetadata;
    remove @5 :Remove;
  }
}

struct Response {
  struct Read {
    metadata @0 :Metadata;
    blob @1 :BlobRequest;
  }

  struct ReadMetadata {
    metadata @0 :Metadata;
  }

  struct Write {
    blob @0 :BlobRequest;
  }

  struct WriteMetadata {
    metadata @0 :Metadata;
  }

  struct Remove {
    metadata @0 :Metadata;
  }

  struct Metadata {
    metadata @0 :Data;
    size @1 :UInt32;
    expireAt @2 :Timestamp;
  }

  struct BlobRequest {
    endpoint @0 :Endpoint;
    token @1 :Token;
  }

  union {
    cancel @0 :Void;
    read @1 :Read;
    readMetadata @2 :ReadMetadata;
    write @3 :Write;
    writeMetadata @4 :WriteMetadata;
    remove @5 :Remove;
  }
}

struct Error {
  union {
    server @0 :Void;

    unavailable @1 :Void;

    invalidRequest @2 :Void;
    # More refined invalid request errors.
    maxKeySizeExceeded @3 :UInt32;
    maxMetadataSizeExceeded @4 :UInt32;
    maxBlobSizeExceeded @5 :UInt32;
  }
}
