BEGIN;

CREATE TABLE IF NOT EXISTS dkvcache (
  key BLOB UNIQUE NOT NULL,
  value BLOB NOT NULL,
  expire_at INTEGER,
  recency INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_dkvcache_key ON dkvcache (key);
CREATE INDEX IF NOT EXISTS ix_dkvcache_expire_at ON dkvcache (expire_at);
CREATE INDEX IF NOT EXISTS ix_dkvcache_recency ON dkvcache (recency);

COMMIT;
