"""Harvest key signals from lab data stores into one constellation snapshot."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import SCHEMA_VERSION
from .store import GalaxyStore, lab_data


def _safe_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"value": data}
    except (OSError, json.JSONDecodeError):
        return None


def _sqlite_count(db: Path, table: str, where: str = "") -> Optional[int]:
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(str(db))
        try:
            q = "SELECT COUNT(*) FROM %s" % table
            if where:
                q += " WHERE " + where
            return int(conn.execute(q).fetchone()[0])
        finally:
            conn.close()
    except (sqlite3.Error, OSError, TypeError, ValueError):
        return None


def _sqlite_query(db: Path, sql: str, params: Tuple[Any, ...] = ()) -> List[Any]:
    if not db.is_file():
        return []
    try:
        conn = sqlite3.connect(str(db))
        try:
            return list(conn.execute(sql, params).fetchall())
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return []


def _star(
    name: str,
    *,
    status: str,
    magnitude: float,
    metrics: Dict[str, Any],
    note: str = "",
) -> Dict[str, Any]:
    """One star in the constellation. status: bright|stable|dim|dark|alert."""
    return {
        "name": name,
        "status": status,
        "magnitude": round(max(0.0, min(1.0, float(magnitude))), 3),
        "metrics": metrics,
        "note": note,
    }


def collect_tokens(root: Path) -> Dict[str, Any]:
    db = root / "token_policy.db"
    n = _sqlite_count(db, "audits") or 0
    completed = _sqlite_count(db, "audits", "actual_tokens IS NOT NULL") or 0
    by_mode: Dict[str, int] = {}
    for mode, c in _sqlite_query(db, "SELECT mode, COUNT(*) FROM audits GROUP BY mode"):
        by_mode[str(mode)] = int(c)
    # crude quality: complete rate + prefer local/short dominance
    complete_rate = (completed / n) if n else 0.0
    short_local = by_mode.get("short", 0) + by_mode.get("local", 0)
    efficiency = (short_local / n) if n else 0.5
    mag = 0.4 * complete_rate + 0.6 * min(1.0, efficiency + 0.2)
    if n == 0:
        status, note = "dark", "no token audits yet"
    elif complete_rate < 0.15:
        status, note = "dim", "few completed audits (route without complete)"
    elif by_mode.get("deep", 0) > n * 0.25:
        status, note = "alert", "deep mode share elevated"
    else:
        status, note = "bright" if mag >= 0.7 else "stable", "token control plane active"
    return _star(
        "tokens",
        status=status,
        magnitude=mag if n else 0.1,
        metrics={
            "n_audits": n,
            "n_completed": completed,
            "complete_rate": round(complete_rate, 3),
            "by_mode": by_mode,
        },
        note=note,
    )


def collect_research(root: Path) -> Dict[str, Any]:
    kpi = _safe_json(root / "research_kpi.json") or {}
    db = root / "research_log.db"
    n_tasks = _sqlite_count(db, "tasks") or 0
    n_open = _sqlite_count(db, "tasks", "status='open'") or 0
    n_done = int(kpi.get("n_completed_logs") or 0) or (
        _sqlite_count(db, "tasks", "status='completed'") or 0
    )
    success = float(kpi.get("accepted_patch_rate") or 0.0)
    if n_tasks == 0 and n_done == 0:
        return _star(
            "research",
            status="dark",
            magnitude=0.1,
            metrics={"n_tasks": 0, "n_open": 0, "kpi": {}},
            note="no research logs",
        )
    mag = 0.5 * min(1.0, n_done / 20.0) + 0.5 * (success if success else 0.5)
    status = "bright" if mag >= 0.7 else ("stable" if n_done else "dim")
    return _star(
        "research",
        status=status,
        magnitude=mag,
        metrics={
            "n_tasks": n_tasks,
            "n_completed": n_done,
            "n_open": n_open,
            "accepted_patch_rate": kpi.get("accepted_patch_rate"),
            "test_pass_rate": kpi.get("test_pass_rate"),
            "avg_tokens_per_success": kpi.get("average_tokens_per_success"),
            "recovery_rate": kpi.get("recovery_rate_after_failure"),
        },
        note="golden workflow log",
    )


def collect_graph(root: Path) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    try:
        import sys

        repo = os.environ.get("GROK_LAB_REPO")
        if repo:
            sys.path.insert(0, str(Path(repo) / "modules"))
        else:
            # collector lives modules/galaxy → parents[1]=modules
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from graph.logstore import GraphLog  # type: ignore

        stats = GraphLog().stats()
        metrics = dict(stats)
    except Exception:
        n = _sqlite_count(root / "graph_routes.db", "nodes")
        metrics = {"n_nodes": n or 0}
    breakers = _safe_json(root / "graph_breakers.json") or {}
    metrics["breakers_keys"] = list(breakers.keys())[:12] if breakers else []
    n = int(metrics.get("n_nodes") or 0)
    if n == 0:
        return _star(
            "graph",
            status="dim",
            magnitude=0.25,
            metrics=metrics,
            note="no graph route nodes yet",
        )
    drop = metrics.get("context_dropped_frac")
    mag = min(1.0, 0.3 + n / 50.0)
    if drop is not None and float(drop) > 0.6:
        status = "alert"
        note = "high context drop fraction"
    else:
        status = "stable"
        note = "L2 context routing log"
    return _star("graph", status=status, magnitude=mag, metrics=metrics, note=note)


def collect_compound(root: Path) -> Dict[str, Any]:
    state = _safe_json(root / "compound_state.json") or {}
    canary = _safe_json(root / "canary_state.json") or {}
    highest = state.get("highest_round") or state.get("round") or "unknown"
    product = state.get("product") or state.get("lever_product")
    mag = 0.5
    if isinstance(product, (int, float)):
        mag = min(1.0, float(product) / 30.0)
    status = "stable" if state else "dark"
    return _star(
        "compound",
        status=status if state else "dark",
        magnitude=mag if state else 0.1,
        metrics={
            "highest_round": highest,
            "product": product,
            "canary": canary,
            "keys": list(state.keys())[:16],
        },
        note="compounding rounds",
    )


def collect_body(root: Path) -> Dict[str, Any]:
    bodies = root / "bodies"
    n = 0
    if bodies.is_dir():
        try:
            n = sum(1 for p in bodies.iterdir() if not p.name.startswith("."))
        except OSError:
            n = 0
    # try body store if present
    outcomes_avg = None
    try:
        import sys

        repo = os.environ.get("GROK_LAB_REPO")
        if repo:
            sys.path.insert(0, str(Path(repo) / "modules"))
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from body.store import BodyStore  # type: ignore

        store = BodyStore()
        ids = store.list_ids() if hasattr(store, "list_ids") else []
        if not ids and hasattr(store, "list"):
            try:
                ids = [b.id for b in store.list()]  # type: ignore
            except Exception:
                ids = []
        n = max(n, len(ids or []))
    except Exception:
        pass
    mag = min(1.0, 0.2 + n * 0.2) if n else 0.15
    return _star(
        "body",
        status="stable" if n else "dim",
        magnitude=mag,
        metrics={"n_bodies": n, "avg_outcome": outcomes_avg},
        note="body registry",
    )


def collect_resilience(root: Path) -> Dict[str, Any]:
    # resilience may live in graph_breakers or dedicated state
    breakers = _safe_json(root / "graph_breakers.json") or {}
    n = len(breakers) if isinstance(breakers, dict) else 0
    openish = 0
    if isinstance(breakers, dict):
        for v in breakers.values():
            if isinstance(v, dict):
                st = str(v.get("state") or v.get("status") or "").lower()
                if st in ("open", "degraded", "half-open", "half_open"):
                    openish += 1
    if n == 0:
        status, mag, note = "dim", 0.3, "no breaker state file signals"
    elif openish:
        status, mag, note = "alert", 0.45, "%d breakers not closed" % openish
    else:
        status, mag, note = "bright", 0.85, "breakers calm"
    return _star(
        "resilience",
        status=status,
        magnitude=mag,
        metrics={"n_breakers": n, "not_closed": openish},
        note=note,
    )


def collect_forge(root: Path) -> Dict[str, Any]:
    db = root / "experiments.db"
    n_exp = _sqlite_count(db, "experiments") or 0
    n_runs = _sqlite_count(db, "runs") or 0
    mag = min(1.0, 0.2 + (n_exp + n_runs) / 40.0) if (n_exp or n_runs) else 0.15
    status = "stable" if n_exp else "dim"
    return _star(
        "forge",
        status=status,
        magnitude=mag,
        metrics={"n_experiments": n_exp, "n_runs": n_runs},
        note="experiment ledger",
    )


def collect_showroom(root: Path, repo: Optional[Path] = None) -> Dict[str, Any]:
    inbox = root / "showroom" / "inbox"
    n_inbox = 0
    if inbox.is_dir():
        try:
            n_inbox = sum(1 for p in inbox.iterdir() if not p.name.startswith("."))
        except OSError:
            pass
    n_pub = 0
    if repo:
        entries = repo / "showroom" / "entries"
        if entries.is_dir():
            try:
                n_pub = sum(1 for p in entries.iterdir() if p.is_dir())
            except OSError:
                pass
    mag = min(1.0, 0.25 + n_pub * 0.12 + n_inbox * 0.05)
    return _star(
        "showroom",
        status="bright" if n_pub else "dim",
        magnitude=mag,
        metrics={"published": n_pub, "inbox": n_inbox},
        note="portfolio gallery",
    )


def collect_session(root: Path) -> Dict[str, Any]:
    boot = _safe_json(root / "session_token_boot.json") or {}
    if not boot:
        return _star(
            "session",
            status="dark",
            magnitude=0.1,
            metrics={},
            note="no session_token_boot.json",
        )
    policy = boot.get("token_policy") or "unknown"
    mag = 0.9 if policy == "active" else 0.4
    return _star(
        "session",
        status="bright" if policy == "active" else "dim",
        magnitude=mag,
        metrics={
            "token_policy": policy,
            "default_mode": boot.get("default_mode"),
            "budget_tokens": boot.get("budget_tokens"),
            "audit_id": boot.get("audit_id"),
            "ts": boot.get("ts"),
        },
        note="session start token boot",
    )


def collect_health(repo: Optional[Path] = None) -> Dict[str, Any]:
    """Prefer last observatory status.json; do not re-run doctor (expensive)."""
    candidates: List[Path] = []
    if repo:
        candidates.append(repo / "data" / "status.json")
    env_repo = os.environ.get("GROK_LAB_REPO")
    if env_repo:
        candidates.append(Path(env_repo) / "data" / "status.json")
    status_doc: Optional[Dict[str, Any]] = None
    for p in candidates:
        status_doc = _safe_json(p)
        if status_doc:
            break
    if not status_doc:
        return _star(
            "health",
            status="dim",
            magnitude=0.4,
            metrics={},
            note="no status.json — run lab observatory snapshot",
        )
    d = status_doc.get("doctor") or {}
    p = int(d.get("pass") or 0)
    w = int(d.get("warn") or 0)
    f = int(d.get("fail") or 0)
    total = max(1, p + w + f)
    mag = max(0.0, (p + 0.4 * w) / total - 0.15 * f)
    if f > 0:
        st = "alert"
    elif w > 3:
        st = "dim"
    else:
        st = "bright"
    return _star(
        "health",
        status=st,
        magnitude=mag,
        metrics={
            "pass": p,
            "warn": w,
            "fail": f,
            "operational": d.get("operational"),
            "generated_at": status_doc.get("generated_at"),
            "host": status_doc.get("host"),
        },
        note="doctor snapshot",
    )


def health_score(stars: Dict[str, Dict[str, Any]]) -> float:
    if not stars:
        return 0.0
    weights = {
        "tokens": 1.4,
        "research": 1.2,
        "health": 1.3,
        "session": 1.0,
        "graph": 0.8,
        "forge": 0.7,
        "compound": 0.7,
        "body": 0.6,
        "resilience": 0.9,
        "showroom": 0.5,
    }
    num = 0.0
    den = 0.0
    for name, star in stars.items():
        w = weights.get(name, 0.5)
        m = float(star.get("magnitude") or 0)
        # penalty for alert
        if star.get("status") == "alert":
            m *= 0.7
        elif star.get("status") == "dark":
            m *= 0.5
        num += w * m
        den += w
    return round(num / den if den else 0.0, 3)


def harvest(
    *,
    root: Optional[Path] = None,
    repo: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build full constellation payload (no side effects)."""
    data = root or lab_data()
    if repo is None:
        env = os.environ.get("GROK_LAB_REPO")
        if env:
            repo = Path(env)
        else:
            # modules/galaxy/collector.py → monorepo
            repo = Path(__file__).resolve().parents[2]

    stars: Dict[str, Dict[str, Any]] = {
        "tokens": collect_tokens(data),
        "research": collect_research(data),
        "graph": collect_graph(data),
        "compound": collect_compound(data),
        "body": collect_body(data),
        "resilience": collect_resilience(data),
        "forge": collect_forge(data),
        "showroom": collect_showroom(data, repo),
        "session": collect_session(data),
        "health": collect_health(repo),
    }
    score = health_score(stars)
    alerts = [n for n, s in stars.items() if s.get("status") == "alert"]
    dark = [n for n, s in stars.items() if s.get("status") == "dark"]
    now = time.time()
    return {
        "schema_version": SCHEMA_VERSION,
        "system": "astro-galaxy",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "ts": now,
        "lab_data": str(data),
        "health_score": score,
        "stars": stars,
        "alerts": alerts,
        "dark": dark,
        "n_stars": len(stars),
        "summary": {
            "bright": sum(1 for s in stars.values() if s.get("status") == "bright"),
            "stable": sum(1 for s in stars.values() if s.get("status") == "stable"),
            "dim": sum(1 for s in stars.values() if s.get("status") == "dim"),
            "dark": len(dark),
            "alert": len(alerts),
        },
    }


def collect_and_persist(
    *,
    store: Optional[GalaxyStore] = None,
    root: Optional[Path] = None,
    repo: Optional[Path] = None,
    source: str = "collect",
) -> Dict[str, Any]:
    """Harvest, write snapshot + daily JSON + optional event for alerts."""
    store = store or GalaxyStore()
    payload = harvest(root=root, repo=repo)
    sid = store.save_snapshot(payload, source=source)
    payload["snapshot_id"] = sid

    # Daily rollup under metrics/daily and galaxy/
    data = root or lab_data()
    day = time.strftime("%Y-%m-%d", time.gmtime(payload["ts"]))
    daily_dir = data / "metrics" / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    gdir = data / "galaxy"
    gdir.mkdir(parents=True, mode=0o700, exist_ok=True)

    daily_path = daily_dir / ("galaxy-%s.json" % day)
    latest_path = gdir / "latest.json"
    text = json.dumps(payload, indent=2, default=str) + "\n"
    daily_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    payload["paths"] = {
        "daily": str(daily_path),
        "latest": str(latest_path),
        "db": str(store.db_path),
    }

    for name in payload.get("alerts") or []:
        star = (payload.get("stars") or {}).get(name) or {}
        store.log_event(
            name,
            "alert",
            star.get("metrics"),
            note=str(star.get("note") or ""),
            source=source,
            ts=payload["ts"],
        )

    store.log_event(
        "core",
        "collect",
        {
            "snapshot_id": sid,
            "health_score": payload["health_score"],
            "summary": payload["summary"],
        },
        note="auto harvest",
        source=source,
        ts=payload["ts"],
    )
    return payload
