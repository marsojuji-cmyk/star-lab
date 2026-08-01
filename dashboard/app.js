/* Mission Control progressive enhancement — reads window.GROK_LAB_STATUS (no fetch). */
(function () {
  "use strict";

  function $(sel) {
    return document.querySelector(sel);
  }

  function setText(sel, text) {
    var el = $(sel);
    if (el) el.textContent = text;
  }

  function severityClass(sev) {
    if (sev === "pass" || sev === "ok" || sev === true) return "on";
    if (sev === "warn") return "amber";
    if (sev === "fail" || sev === false) return "off-bad";
    return "muted";
  }

  function moduleLabel(v) {
    return v || "off";
  }

  function showBanner(msg) {
    var b = $("#status-banner");
    if (!b) return;
    b.hidden = false;
    b.textContent = msg;
  }

  function hideBanner() {
    var b = $("#status-banner");
    if (b) b.hidden = true;
  }

  function findCheck(checks, idPrefix) {
    if (!checks) return null;
    for (var i = 0; i < checks.length; i++) {
      if (checks[i].id === idPrefix || (checks[i].id && checks[i].id.indexOf(idPrefix) === 0)) {
        return checks[i];
      }
    }
    return null;
  }

  function checkOn(checks, id) {
    var c = findCheck(checks, id);
    if (!c) return null;
    return c.severity === "pass";
  }

  function render(status) {
    if (!status || !status.generated_at) {
      showBanner("Run lab dash or lab observatory snapshot to load live status.");
      setText("#score-label", "No snapshot yet · placeholders only");
      var dot = $("#score-dot");
      if (dot) {
        dot.classList.remove("ok", "bad");
        dot.classList.add("amber-dot");
      }
      return;
    }

    hideBanner();
    var d = status.doctor || {};
    var operational = !!d.operational;
    setText(
      "#score-label",
      (operational ? "Operational" : "Needs attention") +
        " · pass=" +
        (d.pass || 0) +
        " warn=" +
        (d.warn || 0) +
        " fail=" +
        (d.fail || 0) +
        " · " +
        (status.generated_at || "")
    );
    var dot = $("#score-dot");
    if (dot) {
      dot.classList.remove("ok", "bad", "amber-dot");
      dot.classList.add(operational ? "ok" : "bad");
    }

    setText("#meta-host", status.host || "—");
    setText("#meta-disk", status.disk_free_home || "—");
    setText("#meta-skills", status.lab_skills_version || "—");
    setText(
      "#meta-ollama",
      (status.ollama_models && status.ollama_models.length
        ? status.ollama_models.join(", ")
        : "none")
    );

    var checks = d.checks || [];
    function tile(id, onText, offText) {
      var on = checkOn(checks, id);
      if (on === null) return "—";
      return on ? onText : offText;
    }

    // Brain / Hands / Terrain tiles when we can map checks
    var map = [
      ["#v-memory", "cfg.memory_enabled", "enabled", "off"],
      ["#v-rules", "file.home_rules", "present", "missing"],
      ["#v-memory-md", "file.global_memory_md", "written", "missing"],
      ["#v-two-pass", "cfg.two_pass_compaction", "on", "off"],
      ["#v-indexing", "cfg.codebase_indexing", "on", "off"],
      ["#v-lsp", "cfg.lsp_tools", "on", "off"],
      ["#v-always", "cfg.always_approve", "always-approve", "other"],
      ["#v-deny", "cfg.deny_rules", "hard blocks", "missing"],
      ["#v-hook", "file.safety_hook", "catastrophic shell", "missing"],
      ["#v-gitignore", "cfg.respect_gitignore", "on", "off"],
      ["#v-autoupdate", "cfg.auto_update", "on", "off"],
      ["#v-theme", "cfg.theme", "tokyonight", "other"],
    ];
    for (var i = 0; i < map.length; i++) {
      var row = map[i];
      var el = $(row[0]);
      if (!el) continue;
      var on = checkOn(checks, row[1]);
      if (on === null) {
        // try safety.allow for hook
        if (row[1] === "file.safety_hook") on = checkOn(checks, "safety.allow");
      }
      if (on === null) continue;
      el.textContent = on ? row[2] : row[3];
      el.className = "v " + (on ? "on" : "off-bad");
    }

    // Modules grid
    var mods = status.modules || {};
    var list = $("#module-list");
    if (list) {
      list.innerHTML = "";
      Object.keys(mods).forEach(function (name) {
        var li = document.createElement("li");
        var k = document.createElement("span");
        k.className = "k";
        k.textContent = name;
        var v = document.createElement("span");
        var val = moduleLabel(mods[name]);
        v.className = "v " + severityClass(val);
        v.textContent = val;
        li.appendChild(k);
        li.appendChild(v);
        list.appendChild(li);
      });
    }

    setText("#showroom-count", String(status.showroom_count != null ? status.showroom_count : 0));
    setText(
      "#showroom-inbox",
      String(status.showroom_inbox_count != null ? status.showroom_inbox_count : 0)
    );

    var safety = status.safety || {};
    setText("#safety-hook", safety.hook ? "on" : "off");
    setText("#safety-deny", safety.deny_rules ? "on" : "off");
    var sh = $("#safety-hook");
    if (sh) sh.className = "v " + (safety.hook ? "on" : "off-bad");
    var sd = $("#safety-deny");
    if (sd) sd.className = "v " + (safety.deny_rules ? "on" : "off-bad");
  }

  function boot() {
    var status = window.GROK_LAB_STATUS;
    render(status);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
