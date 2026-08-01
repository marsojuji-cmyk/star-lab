# Sandbox Range

Curated Seatbelt / Landlock profiles for Grok Star Lab untrusted and review work.

## Profiles

| Profile | Extends | Intent |
|---------|---------|--------|
| `lab-workspace` | `workspace` | Everyday lab dev; write CWD + `~/.grok` + temp; denies `**/.env`, `**/*.pem`, `**/*credentials*` |
| `lab-readonly-review` | `read-only` | Review without writing project files; `restrict_network = true` |
| `lab-untrusted` | `strict` | Third-party / untrusted trees; strict FS + network flag + secret denies |

Source fragment: `profiles.fragment.toml` (in-repo).  
Install target: `~/.grok/sandbox.toml` (`$GROK_HOME/sandbox.toml`).

## Commands

```bash
lab sandbox list
lab sandbox use lab-workspace
lab sandbox install          # missing keys only — never overwrites user values
lab sandbox install --dry-run
lab sandbox test             # live probe; SKIP if grok missing/unauth
```

Use with Grok:

```bash
grok --sandbox lab-workspace
grok --sandbox lab-untrusted -p "review this tree"
```

## Merge policy (K9)

`lab sandbox install` merges **only missing** `[profiles.lab-*]` keys into the
target file:

1. Missing profile table → append full section from the fragment.
2. Existing profile, missing key → add that key only.
3. Same key, same value → no-op.
4. Same key, different value → **conflict**: keep the user value, print manual
   diff instructions. Never clobber.

## macOS network caveat

`restrict_network` blocks **child-process** network on **Linux** (seccomp). On
**macOS (Seatbelt) it is a no-op** — child `curl`/`npm` may still reach the
network. In-process Grok tools (LLM API, web_search) are never blocked on either
platform.

## Offline / doctor

Live Seatbelt enforcement requires `grok` and a working sandbox backend.
`lab sandbox test` exits **0 with SKIP** when `grok` is missing, unauthenticated,
or the probe is inconclusive — it must not fail core doctor on offline hosts.
Profile **install** and **list** are fully offline.
