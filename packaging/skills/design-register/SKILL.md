---
name: design-register
description: Register design docs in Grok Star Lab Design Studio (list/open/register; optional showroom inbox)
---

# Design register

When the user finishes a design doc or asks to catalog architecture/specs for Grok Star Lab:

1. **Register** the markdown path (offline, local only):
   ```bash
   lab design register <path> [--project NAME] [--slug SLUG] [--showroom]
   ```
   - Copies into the canonical tree when `--project` is known:
     `~/Projects/<project>/docs/design/<YYYY-MM-DD>-<slug>.md`
   - Use `--no-copy` to record a pointer only.
   - `--showroom` writes **inbox only** (`~/.grok/lab/showroom/inbox/`) — never auto-publish.

2. **List** registered docs:
   ```bash
   lab design list [--project NAME] [--json]
   ```

3. **Open** by id, slug, or path:
   ```bash
   lab design open <id|slug|path> [--project NAME]
   ```

4. After a `/design` skill loop (or similar), prefer registering the durable doc under the project `docs/design/` tree so Knowledge Crucible and Showroom can find it later.

5. Do **not** auto-publish Showroom entries from this skill. Publish is explicit: `lab showroom publish <capture_id>`.

If `lab design` is missing, ensure the lab CLI is on PATH (`lab install` / `~/.local/bin/lab`).
