@0xef3093bf45c36409;

using Timestamp = UInt64;

struct BlobMetadata {
  # TODO: Add a checksum to detect key corruption.
  key @0 :Data;
  metadata @1 :Data;
  expireAt @2 :Timestamp;
}
