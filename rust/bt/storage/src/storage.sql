BEGIN;

CREATE TABLE IF NOT EXISTS torrent (
  info_hash BLOB PRIMARY KEY,
  info BLOB NOT NULL,
  metainfo BLOB
);

COMMIT;
