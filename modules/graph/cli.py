#!/usr/bin/env python3
"""lab graph — token-constrained context routing (L2 / RCR-style)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "modules"))

from graph.router import route_context, ablate
from graph.allocator import allocate_budget
from graph.logstore import GraphLog


def _load_memory(path: Optional[str], inline: Optional[str]) -> List[Dict[str, Any]]:
    if inline:
        data = json.loads(inline)
    elif path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        return []
    if isinstance(data, dict) and "memory" in data:
        data = data["memory"]
    if not isinstance(data, list):
        raise ValueError("memory must be a JSON list of items")
    return data


def cmd_route(args: argparse.Namespace) -> int:
    try:
        memory = _load_memory(args.memory, args.memory_json)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    budget = args.budget
    if budget is None and args.parent_budget is not None:
        budget = allocate_budget(
            args.role, parent_context_budget=args.parent_budget, stage=args.stage
        )
    result = route_context(
        memory,
        args.role,
        args.stage,
        budget=budget,
        parent_context_budget=args.parent_budget,
        policy=args.policy,
    )
    d = result.to_dict()
    if args.log:
        log = GraphLog()
        nid = log.log_route_result(
            d,
            session_id=args.session_id or "",
            parent_task_id=args.task_id or "",
            downstream=(args.downstream or "").split(",") if args.downstream else None,
        )
        d["log_id"] = nid
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print(f"graph: route role={result.role} stage={result.stage} policy={result.policy}")
        print(f"  budget:     {result.budget}")
        print(f"  passed:     {result.n_passed} slices / {result.tokens_passed} tok")
        print(f"  summarized: {result.n_summarized} / {result.tokens_summarized} tok")
        print(f"  dropped:    {result.n_dropped} / {result.tokens_dropped} tok")
        if d.get("log_id"):
            print(f"  log_id:     {d['log_id']}")
        for dec in result.decisions[:12]:
            print(
                f"  - {dec.action:9} id={dec.id} α={dec.alpha:.2f} "
                f"tok={dec.tokens}→{dec.tokens_after} ({dec.reason})"
            )
        if len(result.decisions) > 12:
            print(f"  … {len(result.decisions) - 12} more")
    return 0


def cmd_log_node(args: argparse.Namespace) -> int:
    log = GraphLog()
    nid = log.log_node(
        role=args.role,
        stage=args.stage or "",
        input_tokens=args.in_tokens,
        output_tokens=args.out_tokens,
        budget_tokens=args.budget,
        context_tokens_used=args.context_tokens,
        policy=args.policy or "",
        n_passed=args.n_passed,
        n_summarized=args.n_summarized,
        n_dropped=args.n_dropped,
        tokens_passed=args.tokens_passed,
        tokens_summarized=args.tokens_summarized,
        tokens_dropped=args.tokens_dropped,
        session_id=args.session_id or "",
        parent_task_id=args.task_id or "",
        downstream=(args.downstream or "").split(",") if args.downstream else None,
    )
    if args.json:
        print(json.dumps({"id": nid}))
    else:
        print(f"graph: logged node id={nid} role={args.role}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    log = GraphLog()
    s = log.stats()
    if args.json:
        print(json.dumps(s, indent=2))
    else:
        print("═══ Graph context routing stats (L2) ═══")
        print(f"n_nodes:                 {s.get('n_nodes')}")
        print(f"tokens_per_agent_round:  {s.get('tokens_per_agent_round')}")
        print(f"avg_context_tokens:      {s.get('avg_context_tokens')}")
        print(f"context_dropped_frac:    {s.get('context_dropped_frac')}")
        print(f"tokens_passed/sum/drop:  {s.get('tokens_passed')}/{s.get('tokens_summarized')}/{s.get('tokens_dropped')}")
        print(f"north_star:              {s.get('north_star')}")
        for pol, v in (s.get("by_policy") or {}).items():
            print(f"  policy {pol or '—'}: n={v['n']} avg_ctx={v['avg_ctx']}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    log = GraphLog()
    rows = log.recent(limit=args.limit)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(
                f"{r['id']} role={r.get('role')} stage={r.get('stage')} "
                f"policy={r.get('policy')} ctx={r.get('context_tokens_used')} "
                f"drop={r.get('tokens_dropped')}"
            )
    return 0


def cmd_ablate(args: argparse.Namespace) -> int:
    try:
        memory = _load_memory(args.memory, args.memory_json)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    table = ablate(
        memory,
        args.role,
        args.stage,
        budget=args.budget,
        parent_context_budget=args.parent_budget,
    )
    # optionally log each arm as synthetic node
    if args.log:
        log = GraphLog()
        for pol, arm in table["arms"].items():
            log.log_node(
                role=args.role,
                stage=args.stage,
                budget_tokens=arm["budget"],
                context_tokens_used=arm["tokens_carried"],
                policy=f"ablate_{pol}",
                n_passed=arm["n_passed"],
                n_summarized=arm["n_summarized"],
                n_dropped=arm["n_dropped"],
                tokens_passed=arm["tokens_carried"] if pol != "full" else arm["tokens_carried"],
                tokens_dropped=arm["tokens_dropped"],
                parent_task_id=args.task_id or "",
                payload={"ablation": pol, "arm": arm},
            )
    if args.json:
        print(json.dumps(table, indent=2))
    else:
        print("═══ Graph ablation: full vs budgeted vs role_aware ═══")
        print(f"role={table['role']} stage={table['stage']} budget={table['budget']}")
        for pol, arm in table["arms"].items():
            save = arm.get("vs_full_save_frac")
            save_s = f"{save*100:.1f}%" if save is not None else "—"
            print(
                f"  {pol:12} carried={arm['tokens_carried']:6} "
                f"dropped={arm['tokens_dropped']:6} "
                f"pass/sum/drop={arm['n_passed']}/{arm['n_summarized']}/{arm['n_dropped']} "
                f"save_vs_full={save_s}"
            )
        print(f"note: {table['north_star_note']}")
    return 0


def cmd_budget(args: argparse.Namespace) -> int:
    b = allocate_budget(
        args.role,
        parent_context_budget=args.parent_budget,
        stage=args.stage or "",
    )
    out = {"role": args.role, "stage": args.stage, "budget": b}
    print(json.dumps(out, indent=2) if args.json else f"graph: budget role={args.role} → {b}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="lab graph",
        description="Token-constrained multi-agent context routing (RCR-style L2)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("route-context", help="Route memory slices under per-role budget")
    r.add_argument("--role", required=True)
    r.add_argument("--stage", default="default")
    r.add_argument("--budget", type=int, default=None)
    r.add_argument("--parent-budget", type=int, default=None, help="L1 max_context_tokens envelope")
    r.add_argument("--policy", default="role_aware", choices=["full", "budgeted", "role_aware"])
    r.add_argument("--memory", help="Path to JSON list of memory items")
    r.add_argument("--memory-json", help="Inline JSON list")
    r.add_argument("--log", action="store_true", help="Persist route to graph_routes.db")
    r.add_argument("--session-id", default="")
    r.add_argument("--task-id", default="")
    r.add_argument("--downstream", default="", help="Comma-separated downstream node ids")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_route)

    ln = sub.add_parser("log-node", help="Log a graph node invocation")
    ln.add_argument("--role", required=True)
    ln.add_argument("--stage", default="")
    ln.add_argument("--in-tokens", type=int, default=0)
    ln.add_argument("--out-tokens", type=int, default=0)
    ln.add_argument("--budget", type=int, default=None)
    ln.add_argument("--context-tokens", type=int, default=None)
    ln.add_argument("--policy", default="")
    ln.add_argument("--n-passed", type=int, default=0)
    ln.add_argument("--n-summarized", type=int, default=0)
    ln.add_argument("--n-dropped", type=int, default=0)
    ln.add_argument("--tokens-passed", type=int, default=0)
    ln.add_argument("--tokens-summarized", type=int, default=0)
    ln.add_argument("--tokens-dropped", type=int, default=0)
    ln.add_argument("--session-id", default="")
    ln.add_argument("--task-id", default="")
    ln.add_argument("--downstream", default="")
    ln.add_argument("--json", action="store_true")
    ln.set_defaults(func=cmd_log_node)

    st = sub.add_parser("stats", help="Aggregate graph routing stats")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_stats)

    ls = sub.add_parser("list", help="Recent node logs")
    ls.add_argument("--limit", type=int, default=20)
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    ab = sub.add_parser("ablate", help="full vs budgeted vs role_aware comparison")
    ab.add_argument("--role", required=True)
    ab.add_argument("--stage", default="default")
    ab.add_argument("--budget", type=int, default=None)
    ab.add_argument("--parent-budget", type=int, default=None)
    ab.add_argument("--memory", help="Path to JSON memory list")
    ab.add_argument("--memory-json", help="Inline JSON list")
    ab.add_argument("--log", action="store_true")
    ab.add_argument("--task-id", default="")
    ab.add_argument("--json", action="store_true")
    ab.set_defaults(func=cmd_ablate)

    bu = sub.add_parser("budget", help="Show allocated B_i for a role")
    bu.add_argument("--role", required=True)
    bu.add_argument("--stage", default="")
    bu.add_argument("--parent-budget", type=int, default=None)
    bu.add_argument("--json", action="store_true")
    bu.set_defaults(func=cmd_budget)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
