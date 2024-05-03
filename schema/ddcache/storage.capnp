@0xef3093bf45c36409;

struct BlobMetadata {
  # TODO: Add a checksum to detect key corruption.
  key @0 :Data;
  metadata @1 :Data;
}
