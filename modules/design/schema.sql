-- Grok Star Lab — Design Studio schema (v1)
-- Applied with PRAGMA user_version=1; journal_mode=WAL.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS design_docs (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL,
  project TEXT,
  title TEXT,
  path TEXT NOT NULL,              -- absolute path of registered doc
  source_path TEXT,                -- original path if copied into canonical location
  registered_at TEXT NOT NULL,
  showroom_capture_id TEXT,        -- set when registered with --showroom
  tags TEXT,                       -- JSON array of strings
  notes TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_design_docs_project_slug
  ON design_docs(IFNULL(project, ''), slug);

CREATE INDEX IF NOT EXISTS idx_design_docs_registered
  ON design_docs(registered_at DESC);

CREATE INDEX IF NOT EXISTS idx_design_docs_project
  ON design_docs(project);
