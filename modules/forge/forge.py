# Python 3.9+ Experiment Forge library + run wrapper.
"""SQLite WAL experiment ledger with Markdown dual-write and GROK_LAB_RUN_ID."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# GNU timeout convention for wall-clock abort
EXIT_TIMEOUT = 124

# lib/lab_paths.py — modules/forge is not itself on path; lib is sibling of modules.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_lib = str(_REPO / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from lab_paths import ensure_lab_dirs, lab_data_root, repo_root  # noqa: E402


SCHEMA_VERSION = 1
TERMINAL_STATUSES = frozenset({"completed", "failed", "aborted"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def get_db_path() -> Path:
    return lab_data_root() / "experiments.db"


def experiments_dir() -> Path:
    return lab_data_root() / "experiments"


def run_dir(run_id: str) -> Path:
    return experiments_dir() / run_id


def atomic_write_text(path: Path, content: str) -> None:
    """Write via unique temp file + fsync + os.replace (atomic on same FS)."""
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    tmp = path.with_name("%s.%s.tmp" % (path.name, uuid.uuid4().hex[:8]))
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _git_sha(cwd: Optional[Path] = None) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=5,
            check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _json_loads(s: Optional[str], default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default


class ForgeStore:
    """SQLite store for experiments + runs under lab data root."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        ensure_lab_dirs()
        self.db_path = Path(db_path) if db_path else get_db_path()
        self.db_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        schema_path = _HERE / "schema.sql"
        with self.connect() as conn:
            ver = conn.execute("PRAGMA user_version").fetchone()[0]
            if ver < SCHEMA_VERSION:
                sql = schema_path.read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
                conn.commit()

    # ── experiments ──────────────────────────────────────────────

    def get_or_create_experiment(
        self,
        name: str,
        project: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiments WHERE name = ? AND IFNULL(project,'') = IFNULL(?, '')",
                (name, project),
            ).fetchone()
            if row:
                return dict(row)
            exp_id = new_id()
            now = utc_now_iso()
            tags_json = json.dumps(list(tags) if tags else [])
            conn.execute(
                "INSERT INTO experiments (id, name, project, description, tags, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (exp_id, name, project, description, tags_json, now),
            )
            conn.commit()
            return {
                "id": exp_id,
                "name": name,
                "project": project,
                "description": description,
                "tags": tags_json,
                "created_at": now,
            }

    def get_experiment(self, exp_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiments WHERE id = ?", (exp_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_experiment_by_name(
        self, name: str, project: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if project is not None:
                row = conn.execute(
                    "SELECT * FROM experiments WHERE name = ? AND IFNULL(project,'') = ?",
                    (name, project),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM experiments WHERE name = ? ORDER BY created_at DESC LIMIT 1",
                    (name,),
                ).fetchone()
            return dict(row) if row else None

    def list_experiments(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT e.*, "
                "(SELECT COUNT(*) FROM runs r WHERE r.experiment_id = e.id) AS run_count, "
                "(SELECT r2.status FROM runs r2 WHERE r2.experiment_id = e.id "
                " ORDER BY r2.created_at DESC LIMIT 1) AS last_status "
                "FROM experiments e ORDER BY e.created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ── runs ─────────────────────────────────────────────────────

    def create_run(
        self,
        experiment_id: str,
        command: Sequence[str],
        tags: Optional[Sequence[str]] = None,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        run_id = new_id()
        now = utc_now_iso()
        sha = _git_sha(Path(cwd) if cwd else None)
        session_id = os.environ.get("GROK_SESSION_ID") or os.environ.get(
            "GROK_LAB_SESSION_ID"
        )
        tags_json = json.dumps(list(tags) if tags else [])
        cmd_json = json.dumps(list(command))
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runs "
                "(id, experiment_id, git_sha, session_id, status, created_at, "
                " command, cwd, tags, params, metrics) "
                "VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, '{}', '{}')",
                (
                    run_id,
                    experiment_id,
                    sha,
                    session_id,
                    now,
                    cmd_json,
                    cwd or os.getcwd(),
                    tags_json,
                ),
            )
            conn.commit()
        rd = run_dir(run_id)
        rd.mkdir(parents=True, mode=0o700, exist_ok=True)
        return {
            "id": run_id,
            "experiment_id": experiment_id,
            "git_sha": sha,
            "session_id": session_id,
            "status": "running",
            "created_at": now,
            "command": cmd_json,
            "cwd": cwd or os.getcwd(),
            "tags": tags_json,
            "params": "{}",
            "metrics": "{}",
        }

    def finish_run(
        self,
        run_id: str,
        status: str,
        exit_code: Optional[int],
        duration_ms: int,
    ) -> Dict[str, Any]:
        if status not in TERMINAL_STATUSES:
            raise ValueError("status must be terminal: %s" % status)
        finished = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = ?, duration_ms = ?, "
                "exit_code = ? WHERE id = ?",
                (status, finished, duration_ms, exit_code, run_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise KeyError("run not found: %s" % run_id)
        run = dict(row)
        self.dual_write(run_id)
        return run

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            return dict(row) if row else None

    def list_runs(
        self, experiment_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if experiment_id:
                rows = conn.execute(
                    "SELECT r.*, e.name AS experiment_name, e.project AS project "
                    "FROM runs r JOIN experiments e ON e.id = r.experiment_id "
                    "WHERE r.experiment_id = ? ORDER BY r.created_at DESC LIMIT ?",
                    (experiment_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT r.*, e.name AS experiment_name, e.project AS project "
                    "FROM runs r JOIN experiments e ON e.id = r.experiment_id "
                    "ORDER BY r.created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def log_metric(
        self, run_id: str, key: str, value: float, step: int = 0
    ) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO run_metrics (run_id, key, value, step, logged_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, key, float(value), int(step), now),
            )
            row = conn.execute(
                "SELECT metrics FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            metrics = _json_loads(row["metrics"] if row else None, {})
            metrics[key] = float(value)
            conn.execute(
                "UPDATE runs SET metrics = ? WHERE id = ?",
                (json.dumps(metrics), run_id),
            )
            conn.commit()

    def log_param(self, run_id: str, key: str, value: Any) -> None:
        val_s = value if isinstance(value, str) else json.dumps(value)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO run_params (run_id, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(run_id, key) DO UPDATE SET value = excluded.value",
                (run_id, key, val_s),
            )
            row = conn.execute(
                "SELECT params FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            params = _json_loads(row["params"] if row else None, {})
            params[key] = value
            conn.execute(
                "UPDATE runs SET params = ? WHERE id = ?",
                (json.dumps(params), run_id),
            )
            conn.commit()

    def log_artifact(
        self, run_id: str, path: str, kind: Optional[str] = None
    ) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO run_artifacts (run_id, path, kind, logged_at) "
                "VALUES (?, ?, ?, ?)",
                (run_id, str(path), kind, now),
            )
            conn.commit()

    def dual_write(self, run_id: str) -> Tuple[Path, Path]:
        """Write meta.md + results.json atomically for a run (terminal states)."""
        with self.connect() as conn:
            run_row = conn.execute(
                "SELECT r.*, e.name AS experiment_name, e.project AS project "
                "FROM runs r JOIN experiments e ON e.id = r.experiment_id "
                "WHERE r.id = ?",
                (run_id,),
            ).fetchone()
            if not run_row:
                raise KeyError("run not found: %s" % run_id)
            run = dict(run_row)
            metric_rows = conn.execute(
                "SELECT key, value, step, logged_at FROM run_metrics "
                "WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
            param_rows = conn.execute(
                "SELECT key, value FROM run_params WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            art_rows = conn.execute(
                "SELECT path, kind, logged_at FROM run_artifacts WHERE run_id = ?",
                (run_id,),
            ).fetchall()

        params = _json_loads(run.get("params"), {})
        for pr in param_rows:
            if pr["key"] not in params:
                params[pr["key"]] = pr["value"]
        metrics = _json_loads(run.get("metrics"), {})
        tags = _json_loads(run.get("tags"), [])
        command = _json_loads(run.get("command"), [])

        results = {
            "run_id": run_id,
            "experiment_id": run["experiment_id"],
            "experiment_name": run.get("experiment_name"),
            "project": run.get("project"),
            "status": run["status"],
            "exit_code": run.get("exit_code"),
            "duration_ms": run.get("duration_ms"),
            "created_at": run["created_at"],
            "finished_at": run.get("finished_at"),
            "git_sha": run.get("git_sha"),
            "session_id": run.get("session_id"),
            "command": command,
            "cwd": run.get("cwd"),
            "tags": tags,
            "params": params,
            "metrics": metrics,
            "metric_history": [
                {
                    "key": m["key"],
                    "value": m["value"],
                    "step": m["step"],
                    "logged_at": m["logged_at"],
                }
                for m in metric_rows
            ],
            "artifacts": [
                {"path": a["path"], "kind": a["kind"], "logged_at": a["logged_at"]}
                for a in art_rows
            ],
        }

        meta_lines = [
            "# Forge run `%s`" % run_id,
            "",
            "- **experiment**: %s (`%s`)"
            % (run.get("experiment_name"), run["experiment_id"]),
            "- **project**: %s" % (run.get("project") or "—"),
            "- **status**: `%s`" % run["status"],
            "- **exit_code**: %s" % run.get("exit_code"),
            "- **duration_ms**: %s" % run.get("duration_ms"),
            "- **created_at**: %s" % run["created_at"],
            "- **finished_at**: %s" % (run.get("finished_at") or "—"),
            "- **git_sha**: `%s`" % (run.get("git_sha") or "—"),
            "- **tags**: %s" % (", ".join(tags) if tags else "—"),
            "",
            "## Command",
            "",
            "```",
            " ".join(command) if command else "(none)",
            "```",
            "",
            "## Params",
            "",
        ]
        if params:
            for k, v in sorted(params.items()):
                meta_lines.append("- `%s`: %s" % (k, v))
        else:
            meta_lines.append("_(none)_")
        meta_lines.extend(["", "## Metrics", ""])
        if metrics:
            for k, v in sorted(metrics.items()):
                meta_lines.append("- `%s`: %s" % (k, v))
        else:
            meta_lines.append("_(none)_")
        meta_lines.append("")

        rd = run_dir(run_id)
        results_path = rd / "results.json"
        meta_path = rd / "meta.md"
        atomic_write_json(results_path, results)
        atomic_write_text(meta_path, "\n".join(meta_lines) + "\n")
        return meta_path, results_path


class Forge:
    """
    Child-process API. Requires GROK_LAB_RUN_ID (set by `lab forge run`).

        Forge().log_metric("pass_rate", 1.0)
        Forge(os.environ["GROK_LAB_RUN_ID"]).log_param("model", "dolphin3:latest")
    """

    def __init__(self, run_id: Optional[str] = None) -> None:
        rid = run_id or os.environ.get("GROK_LAB_RUN_ID")
        if not rid:
            raise RuntimeError(
                "GROK_LAB_RUN_ID is not set; run under `lab forge run` "
                "or pass run_id explicitly"
            )
        self.run_id = rid
        self.store = ForgeStore()

    def log_metric(self, key: str, value: float, step: int = 0) -> None:
        self.store.log_metric(self.run_id, key, value, step=step)

    def log_param(self, key: str, value: Any) -> None:
        self.store.log_param(self.run_id, key, value)

    def log_artifact(self, path: Any, kind: Optional[str] = None) -> None:
        self.store.log_artifact(self.run_id, str(path), kind=kind)


def _child_env(run_id: str) -> Dict[str, str]:
    """Build child env: GROK_LAB_* plus PYTHONPATH for zero-boilerplate Forge import."""
    env = os.environ.copy()
    env["GROK_LAB_RUN_ID"] = run_id
    env["GROK_LAB_DATA"] = str(lab_data_root())
    repo = repo_root()
    env["GROK_LAB_REPO"] = str(repo)
    # Prepend modules/ + lib/ so `from forge import Forge` works without path surgery.
    prepend = [str(repo / "modules"), str(repo / "lib")]
    existing = env.get("PYTHONPATH", "")
    if existing:
        env["PYTHONPATH"] = os.pathsep.join(prepend + [existing])
    else:
        env["PYTHONPATH"] = os.pathsep.join(prepend)
    return env


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill child process group (start_new_session) or fall back to proc.kill()."""
    if proc.poll() is not None:
        return
    try:
        # start_new_session=True → child is session/process-group leader
        os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass


def _stream_child(
    proc: subprocess.Popen,
    logf: Any,
    timeout: Optional[float],
) -> Tuple[Optional[int], str]:
    """
    Tee child stdout (stderr merged) to terminal + log; enforce wall-clock timeout.

    Reader runs in a thread so blocking reads never prevent timeout. Returns
    (exit_code, status_hint) where status_hint is '' | 'aborted'.
    """
    assert proc.stdout is not None
    status_hint = ""
    exit_code: Optional[int] = None

    def reader() -> None:
        try:
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
                logf.write(chunk)
                logf.flush()
        except (ValueError, OSError):
            # pipe closed after kill
            pass

    thr = threading.Thread(target=reader, name="forge-stdout", daemon=True)
    thr.start()
    try:
        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            exit_code = EXIT_TIMEOUT
            status_hint = "aborted"
            print("\nforge: aborted (timeout)", file=sys.stderr)
        except KeyboardInterrupt:
            _kill_process_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            exit_code = 130
            status_hint = "aborted"
            print("\nforge: aborted (interrupt)", file=sys.stderr)
    finally:
        thr.join(timeout=2.0)
        try:
            proc.stdout.close()
        except OSError:
            pass
    return exit_code, status_hint


def run_command(
    store: ForgeStore,
    exp_name: str,
    command: Sequence[str],
    project: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
    timeout: Optional[float] = None,
) -> int:
    """
    Create experiment/run, set GROK_LAB_RUN_ID, exec command, dual-write, return exit code.

    Forge process exit code == child exit code (CI-friendly).
    Timeout → status=aborted, exit 124 (GNU timeout convention).
    """
    if not command:
        raise ValueError("command is required")

    exp = store.get_or_create_experiment(exp_name, project=project, tags=tags)
    run = store.create_run(exp["id"], command, tags=tags, cwd=os.getcwd())
    run_id = run["id"]
    rd = run_dir(run_id)
    console_path = rd / "console.log"

    env = _child_env(run_id)

    print("forge: run_id=%s exp=%s status=running" % (run_id, exp_name), file=sys.stderr)
    print("forge: cmd=%s" % " ".join(command), file=sys.stderr)

    t0 = time.monotonic()
    exit_code: Optional[int] = None
    status = "failed"

    try:
        with open(console_path, "wb") as logf:
            proc = subprocess.Popen(
                list(command),
                env=env,
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            exit_code, status_hint = _stream_child(proc, logf, timeout)
            if status_hint == "aborted":
                status = "aborted"
    except FileNotFoundError:
        print("forge: command not found: %s" % command[0], file=sys.stderr)
        exit_code = 127
        status = "failed"
    except OSError as exc:
        print("forge: failed to start: %s" % exc, file=sys.stderr)
        exit_code = 126
        status = "failed"

    duration_ms = int((time.monotonic() - t0) * 1000)

    if status != "aborted":
        if exit_code == 0:
            status = "completed"
        else:
            status = "failed"

    store.finish_run(run_id, status, exit_code, duration_ms)

    # Showcase tag hook (optional; showroom may not be installed yet).
    tags_list = list(tags) if tags else []
    if status == "completed" and "showcase" in tags_list:
        _try_showcase_capture(run_id)

    print(
        "forge: run_id=%s status=%s exit_code=%s duration_ms=%s"
        % (run_id, status, exit_code, duration_ms),
        file=sys.stderr,
    )
    return int(exit_code if exit_code is not None else 1)


def _try_showcase_capture(run_id: str) -> None:
    """Best-effort showroom inbox capture when tag showcase + completed."""
    try:
        showroom_path = repo_root() / "modules" / "showroom"
        if not showroom_path.is_dir():
            return
        if str(showroom_path) not in sys.path:
            sys.path.insert(0, str(showroom_path))
        # Optional module — ignore if missing.
        import capture  # type: ignore

        if hasattr(capture, "capture_from_forge"):
            capture.capture_from_forge(run_id)
    except Exception:
        pass
