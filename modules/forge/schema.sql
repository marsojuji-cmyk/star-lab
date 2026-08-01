-- Grok Star Lab — Experiment Forge schema (v1)
-- Applied with PRAGMA user_version=1; journal_mode=WAL.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS experiments (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  project TEXT,
  description TEXT,
  tags TEXT,                 -- JSON array of strings
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_experiments_name_project
  ON experiments(name, IFNULL(project, ''));

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  git_sha TEXT,
  session_id TEXT,
  status TEXT NOT NULL CHECK(status IN ('running','completed','failed','aborted')),
  created_at TEXT NOT NULL,
  finished_at TEXT,
  duration_ms INTEGER,
  exit_code INTEGER,
  command TEXT,              -- JSON array of argv
  cwd TEXT,
  tags TEXT,                 -- JSON array of strings
  params TEXT,               -- JSON object
  metrics TEXT               -- JSON object (latest values)
);

CREATE INDEX IF NOT EXISTS idx_runs_experiment ON runs(experiment_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

CREATE TABLE IF NOT EXISTS run_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id),
  key TEXT NOT NULL,
  value REAL NOT NULL,
  step INTEGER NOT NULL DEFAULT 0,
  logged_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_metrics_run ON run_metrics(run_id);

CREATE TABLE IF NOT EXISTS run_params (
  run_id TEXT NOT NULL REFERENCES runs(id),
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (run_id, key)
);

CREATE TABLE IF NOT EXISTS run_artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id),
  path TEXT NOT NULL,
  kind TEXT,
  logged_at TEXT NOT NULL
);
