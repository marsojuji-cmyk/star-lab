---
name: token-route
description: Run token-aware routing before expensive Grok work; prefer local/short when EV says so
---

# Token route

Before multi-file refactors, design loops, or multi-agent work:

1. Run `lab tokens route "<user task summary>"`.
2. If **mode=local** or **short**: solve with scripts/doctor/forge/gym smoke first; do not open deep subagent fan-out.
3. If **medium**: normal Grok turn with tight packing (limited retrieval).
4. If **deep**: allow design/subagents only if escalate=true and EV beats local.
5. After the work, if you know token use / quality, call  
   `lab tokens complete --audit-id … --actual-tokens N --quality 0.0-1.0`.

Token awareness is the operating policy, not an afterthought.
