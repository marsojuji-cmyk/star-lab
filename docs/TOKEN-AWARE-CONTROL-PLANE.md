# Token-Aware Control Plane (TACP)

| Field | Value |
|-------|--------|
| **Status** | Implemented (v1 free offline) |
| **Date** | 2026-08-01 |
| **Location** | `modules/tokens/` |
| **CLI** | `lab tokens …` |
| **Inspiration** | LenVM — Length Value Model ([arxiv:2604.27039](https://arxiv.org/abs/2604.27039)) |

---

## Automatic arming (SessionStart)

On **every new Grok session**, a global hook runs without you asking:

| Piece | Path |
|-------|------|
| Hook | `~/.grok/hooks/token-session-start.json` |
| Boot script | `~/.grok/hooks/scripts/session_tokens_boot.sh` |
| Session marker | `~/.grok/lab/session_token_boot.json` |
| Last route JSON | `~/.grok/lab/session_token_last_route.json` |
| Repo canonical | `packaging/hooks/` (installed by `lab install`) |

Boot actions:

1. Ensure `~/.local/bin/lab` → live lab `bin/lab`
2. Set `GROK_TOKEN_POLICY=1` / `GROK_TOKEN_AUTO=1`
3. Run a default `lab tokens route` (session posture = short)
4. Write the marker JSON for the agent to read
5. Print `[token-policy] ACTIVE` into the session scrollback

**Per-task routing is still required** for non-trivial work (`lab tokens route "<task>"`). SessionStart arms the policy; it does not replace task-level EV decisions.

Re-install hooks anytime:

```bash
lab install
# or
bash ~/Projects/grok-home/scripts/install-lab.sh
```

---

## Doctrine

**Token awareness is not an optimization detail; it is the operating policy.**

1. Every task gets a **predicted token horizon** (token-level length/value signal).
2. Every call gets a **budgeted reasoning mode**: `local | short | medium | deep`.
3. Every escalation must **beat the local-resolution baseline** on expected value:

```text
EV(mode) = expected_reward(mode) − λ · predicted_token_spend
choose argmax EV  s.t. confidence gate + hard safety rules
```

Cheap tasks must never burn deep budgets. Long-context deep reasoning only runs when expected gain clears the margin over local/short.

---

## LenVM relationship

| LenVM (paper) | TACP v1 (this lab) |
|---------------|---------------------|
| Trained value head, remaining length as discounted return under constant per-token cost | Same **math shape** for `remaining_value`; free **heuristic drivers** at prompt boundary |
| Token-level during decode | Prompt-boundary estimate + audit of actual spend (decode-time probe optional via `GROK_LENVM_CMD`) |
| Exact length control / LIFEBench | Routing + packing + escalation policy for Grok Build |
| RL-ready value signal | Distill audits → routing rules continuously |

When you can run a real LenVM probe:

```bash
export GROK_LENVM_CMD='python3 /path/to/lenvm_probe.py'
# probe reads task on stdin, prints JSON {predicted_tokens, confidence, drivers?}
```

---

## Policy loop

```text
annotate → route → (execute) → audit actual tokens vs quality → distill rules → redeploy
```

| Stage | Command |
|-------|---------|
| Annotate / route | `lab tokens route "task…"` |
| Record outcome | `lab tokens complete --audit-id ID --actual-tokens N --quality 0.9 --success yes` |
| Measure | `lab tokens audit --stats` |
| Distill | `lab tokens distill` |
| Doctrine | `lab tokens policy` |

---

## Modes

| Mode | Budget (completion) | Use |
|------|---------------------|-----|
| **local** | 0 | doctor/status/list/help; no model |
| **short** | 512 | typo, rename, quick answers |
| **medium** | 2048 | implement feature, review chunk |
| **deep** | 8192 | multi-agent, hard debug, architecture |

Packing knobs (retrieval_k, max_context_tokens, subagents, continuation) are **mode-governed**, not “append everything.”

---

## Diagnostics

Route output lists **drivers**: patterns that push short vs long regimes (LenVM-style interpretability at policy layer).

Audit DB: `~/.grok/lab/token_policy.db` (or `$GROK_LAB_DATA/token_policy.db`).

---

## Env knobs

| Env | Default | Meaning |
|-----|---------|---------|
| `GROK_TOKEN_LAMBDA` | `0.12` | cost weight λ (reward units per **kilotoken**); **tunable control signal**, not a blind rule |
| `GROK_TOKEN_MIN_CONF` | `0.55` | confidence gate for medium/deep |
| `GROK_TOKEN_ESCALATE_MARGIN` | `0.02` | EV must beat local by this |
| `GROK_LENVM_CMD` | unset | external LenVM JSON probe |
| `GROK_LAB_DATA` | `~/.grok/lab` | audit storage |
| `GROK_TOKEN_SHADOW` | `1` | set `0` to disable shadow dual-log |
| `GROK_SESSION_ID` / `GROK_TENANT` | unset / `local` | stamped on shadow rows |

### Closed-loop gates (four-stage progressive delivery)

```bash
lab tokens eval && lab tokens gates
lab tokens shadow compare
lab tokens rollout propose|shadow-ok|start|check|advance|rollback|drill
lab tokens session lock --mode medium --reason tool_loop
lab graph breaker trip --role implementer
```

Stages: **shadow → canary 1–5% → ramp 10/25/50 → full** (window pack + hard stops).  
Full spec: `docs/research/CLOSED-LOOP-GATES.md`

---

## Grok session rule (human)

Before a heavy Grok turn, run:

```bash
lab tokens route "«paste the user ask»"
```

If mode is `local` or `short`, prefer tools/scripts over long reasoning.
If `deep`, allow multi-agent / design loops; still respect packing budgets.
