// lab-audit.rhai — session-tier multi-agent lab audit (K16/K19)
// Installed under ~/.grok/workflows/ for in-session `/workflow lab-audit`.
// Not executed headlessly by lab arena (v1 prints handoff only).

let meta = #{
    name: "lab-audit",
    description: "Multi-agent audit of Grok Star Lab modules, safety, and offline readiness",
    when_to_use: "When verifying lab install health or after module changes",
    phases: [
        #{ title: "Probe", detail: "parallel read-only checks" },
        #{ title: "Synthesize", detail: "single readiness report" },
    ],
};

let probe_schema = #{
    "type": "object",
    "required": ["area", "status", "notes"],
    "properties": #{
        "area": #{ "type": "string" },
        "status": #{ "type": "string" },
        "notes": #{ "type": "string" },
    },
};

let report_schema = #{
    "type": "object",
    "required": ["headline", "score_hint", "must_fix", "strengths"],
    "properties": #{
        "headline": #{ "type": "string" },
        "score_hint": #{ "type": "string" },
        "must_fix": #{ "type": "array", "items": #{ "type": "string" } },
        "strengths": #{ "type": "array", "items": #{ "type": "string" } },
    },
};

phase("Probe");

let jobs = [
    #{
        prompt: "Read-only audit of Grok Star Lab modules. List modules/ under the lab repo (GROK_LAB_REPO or ~/Projects/grok-home). Report area=modules, status=ok|warn|fail, notes on missing dirs. Do not modify anything.",
        label: "probe:modules",
        capability_mode: "read-only",
        output_schema: probe_schema,
    },
    #{
        prompt: "Read-only audit of safety rails. Check ~/.grok/hooks/safety-guard.json and ~/.grok/hooks/scripts/safety_guard.py exist. Report area=safety, status=ok|warn|fail, concise notes. Do not modify anything.",
        label: "probe:safety",
        capability_mode: "read-only",
        output_schema: probe_schema,
    },
    #{
        prompt: "Read-only audit of lab data root. Check ~/.grok/lab (or GROK_LAB_DATA) exists with experiments/metrics dirs and packaging VERSION pin if present. Report area=lab-data, status=ok|warn|fail. Do not modify anything.",
        label: "probe:lab-data",
        capability_mode: "read-only",
        output_schema: probe_schema,
    },
    #{
        prompt: "Read-only check of offline tooling: bin/lab, modules/arena, modules/forge presence; note ollama only if discoverable without network assumptions. Report area=offline-tooling, status=ok|warn|fail. Do not modify anything.",
        label: "probe:offline",
        capability_mode: "read-only",
        output_schema: probe_schema,
    },
];

let probes = parallel(jobs);

phase("Synthesize");

let synthesis = agent(#{
    prompt: "Synthesize these lab-audit probe results into one readiness report. "
        + "probes=" + probes + ". "
        + "headline = one sentence. score_hint = ok|warn|fail. "
        + "must_fix = actionable list (empty if healthy). strengths = what is solid.",
    label: "synthesize:lab-audit",
    capability_mode: "read-only",
    output_schema: report_schema,
});

print("lab-audit report: " + synthesis);
