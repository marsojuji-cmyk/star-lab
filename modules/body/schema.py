"""Body dataclass + shared mode ranking (single MODE_RANK for body/breaker)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1

# Shared with breaker/resilience — do not fork ranks.
MODE_RANK = {"local": 0, "short": 1, "medium": 2, "deep": 3}


def min_mode(a: str, b: str) -> str:
    """Return the lower-autonomy mode (never escalates)."""
    ra, rb = MODE_RANK.get(a or "short", 1), MODE_RANK.get(b or "short", 1)
    return a if ra <= rb else b


def apply_mode_caps(
    mode: str,
    *,
    locked: bool,
    body_cap: Optional[str],
    breaker_cap: Optional[str],
    preferred_store: Optional[Dict[str, Any]] = None,
) -> str:
    """
    If locked: return mode unchanged; record preferred_mode_cap if caps want lower.
    If not locked: min_mode(mode, body_cap, breaker_cap).
    """
    want = mode
    for cap in (body_cap, breaker_cap):
        if cap:
            want = min_mode(want, cap)
    if locked:
        if preferred_store is not None and want != mode:
            preferred_store["preferred_mode_cap"] = want
        return mode
    return want


@dataclass
class BodyLimits:
    mode_cap: str = "medium"
    budget_tokens_day: int = 100_000
    require_approval_for: List[str] = field(default_factory=list)
    sandbox_profile: Optional[str] = None
    breaker_parent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "BodyLimits":
        d = d or {}
        return cls(
            mode_cap=str(d.get("mode_cap") or "medium"),
            budget_tokens_day=int(d.get("budget_tokens_day") or 100_000),
            require_approval_for=list(d.get("require_approval_for") or []),
            sandbox_profile=d.get("sandbox_profile"),
            breaker_parent=d.get("breaker_parent"),
        )


@dataclass
class Body:
    body_id: str
    kind: str  # lab | project | system
    name: str
    tenant: str = "local"
    identity: Dict[str, Any] = field(default_factory=dict)
    property_map: Dict[str, Any] = field(default_factory=dict)
    contact: Dict[str, Any] = field(default_factory=dict)
    limits: BodyLimits = field(default_factory=BodyLimits)
    organs: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def project_key(self) -> str:
        return (self.property_map or {}).get("project_key") or self.name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "body_id": self.body_id,
            "kind": self.kind,
            "name": self.name,
            "tenant": self.tenant,
            "identity": self.identity,
            "property": self.property_map,
            "contact": self.contact,
            "limits": self.limits.to_dict(),
            "organs": list(self.organs),
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Body":
        return cls(
            schema_version=int(d.get("schema_version") or SCHEMA_VERSION),
            body_id=str(d["body_id"]),
            kind=str(d.get("kind") or "project"),
            name=str(d.get("name") or d["body_id"]),
            tenant=str(d.get("tenant") or "local"),
            identity=dict(d.get("identity") or {}),
            property_map=dict(d.get("property") or {}),
            contact=dict(d.get("contact") or {}),
            limits=BodyLimits.from_dict(d.get("limits")),
            organs=list(d.get("organs") or []),
            meta=dict(d.get("meta") or {}),
        )


def fs_dir_name(body_id: str) -> str:
    """body_id filesystem form: lab:grok-home → lab_grok-home."""
    return (body_id or "unknown").replace(":", "_").replace("/", "_")


DEFAULT_ORGANS = ["forge", "ship", "research", "tokens", "knowledge"]


def default_contact() -> Dict[str, Any]:
    return {
        "channels": [
            {"id": "forge_exit", "enabled": True},
            {"id": "cli_event", "enabled": True},
            {"id": "webhook", "enabled": False},
        ]
    }
