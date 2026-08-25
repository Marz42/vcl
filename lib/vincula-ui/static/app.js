/* Vincula Local Audit UI v2 — stdlib static JS (no build). */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const STATE_CLASS = new Set(["OK", "STALE", "FAIL", "UNKNOWN", "WARN", "-"]);
  const LEVEL_CLASS = new Set(["red", "amber"]);
  const TOKEN_HEADER = "X-Vincula-UI-Token";

  /** Live probe payload from POST /api/refresh/probe (does not write last-status). */
  let liveProbeOverlay = null;

  function uiToken() {
    const meta = document.querySelector('meta[name="vcl-ui-token"]');
    return (meta && meta.getAttribute("content")) || "";
  }

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      el.hidden = true;
    }, 4000);
  }

  async function api(path, opts) {
    const headers = Object.assign({}, (opts && opts.headers) || {});
    headers[TOKEN_HEADER] = uiToken();
    const res = await fetch(path, Object.assign({}, opts || {}, { headers }));
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch (_) {
      throw new Error(text || res.statusText);
    }
    if (!res.ok) {
      throw new Error((data && data.error) || res.statusText);
    }
    return data;
  }

  function statePill(v) {
    const raw = v == null || v === "" ? "-" : String(v);
    const cls = STATE_CLASS.has(raw) ? raw : "UNKNOWN";
    return `<span class="state ${cls}">${escapeHtml(raw)}</span>`;
  }

  function warnLevel(level) {
    const raw = String(level || "amber");
    return LEVEL_CLASS.has(raw) ? raw : "amber";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function human(n) {
    let v = Number(n) || 0;
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    for (let i = 0; i < units.length; i++) {
      if (v < 1024 || i === units.length - 1) {
        return i === 0 ? `${v} ${units[i]}` : `${v.toFixed(1)} ${units[i]}`;
      }
      v /= 1024;
    }
    return `${n} B`;
  }

  function defaultWindow() {
    const to = new Date();
    const from = new Date(to.getTime() - 7 * 24 * 3600 * 1000);
    const iso = (d) => d.toISOString().replace(/\.\d{3}Z$/, "Z");
    return { from: iso(from), to: iso(to) };
  }

  function showPage(name) {
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.page === name));
    $$(".page").forEach((p) => p.classList.toggle("active", p.id === `page-${name}`));
  }

  function renderWarnings(list) {
    const bar = $("#warn-bar");
    const items = list || [];
    if (!items.length) {
      bar.hidden = true;
      bar.innerHTML = "";
      return;
    }
    bar.hidden = false;
    bar.innerHTML = items
      .slice(0, 12)
      .map(
        (w) =>
          `<span class="chip ${warnLevel(w.level)}">${escapeHtml(w.message || w.code)}</span>`
      )
      .join("");
  }

  function table(headers, rowsHtml) {
    return `<table><thead><tr>${headers
      .map((h) => `<th>${h}</th>`)
      .join("")}</tr></thead><tbody>${rowsHtml}</tbody></table>`;
  }

  function renderWorkspaceStrip(el, workspace) {
    if (!el) return;
    if (!workspace) {
      el.hidden = true;
      return;
    }
    const conflict = workspace.conflict || "absent";
    const fid = workspace.fleet_id || "—";
    const rev = workspace.revision != null ? workspace.revision : "—";
    if (!workspace.active) {
      el.hidden = false;
      el.innerHTML =
        "Workspace: <strong>absent</strong> — run <code>vcl-fleet workspace init</code>, then adopt/provision.";
      return;
    }
    el.hidden = false;
    el.innerHTML = `Workspace fleet_id=<code>${escapeHtml(
      fid
    )}</code> revision=${escapeHtml(String(rev))} conflict=<strong>${escapeHtml(
      conflict
    )}</strong>`;
  }

  function updateLiveProbeStrip() {
    const el = $("#live-probe-strip");
    if (!el) return;
    if (!liveProbeOverlay) {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    const ts = liveProbeOverlay.controller_utc || "—";
    const ok = liveProbeOverlay.ok !== false;
    el.hidden = false;
    el.innerHTML = `Live probe (${escapeHtml(ts)}): ${ok ? "ok" : "degraded"} — table below shows live SSH until Sync/Verify reloads cache.`;
  }

  function mergeLiveNodes(cacheNodes) {
    const base = cacheNodes || [];
    if (!liveProbeOverlay || !Array.isArray(liveProbeOverlay.nodes)) {
      return base;
    }
    const byName = {};
    for (const n of base) {
      if (n && n.name) byName[n.name] = { ...n };
    }
    for (const p of liveProbeOverlay.nodes) {
      if (!p || !p.name) continue;
      const prev = byName[p.name] || {};
      byName[p.name] = {
        ...prev,
        ...p,
        last_sync_at: prev.last_sync_at || p.last_sync_at,
      };
    }
    const order = base.map((n) => n.name).filter(Boolean);
    const extra = Object.keys(byName).filter((k) => !order.includes(k));
    return order.concat(extra).map((name) => byName[name]);
  }

  function renderNodesTable(container, data) {
    if (!container) return;
    renderWarnings(data.warnings);
    renderWorkspaceStrip($("#nodes-workspace-strip"), data.workspace);
    const merged = mergeLiveNodes(data.nodes);
    const live = Boolean(liveProbeOverlay);
    const rows = merged
      .map(
        (n) =>
          `<tr class="clickable${live ? " live-row" : ""}" data-node="${escapeHtml(n.name)}">
            <td>${escapeHtml(n.name)}${live ? ' <span class="muted">live</span>' : ""}</td>
            <td>${statePill(n.ssh)}</td>
            <td>${statePill(n.proxy)}</td>
            <td>${statePill(n.accounting)}</td>
            <td>${escapeHtml(n.version || "—")}</td>
            <td>${statePill(n.clock || "-")}</td>
            <td>${escapeHtml(n.last_sync_at || "—")}</td>
          </tr>`
      )
      .join("");
    container.innerHTML = rows
      ? table(
          ["NAME", "SSH", "PROXY", "ACCOUNTING", "VERSION", "CLOCK", "LAST_SYNC"],
          rows
        )
      : `<p class="empty">No nodes in fleet.json. Run <code>vcl-fleet workspace init</code> then <code>node adopt</code> / <code>node provision</code>.</p>`;
    container.querySelectorAll("tr.clickable").forEach((tr) => {
      tr.addEventListener("click", () => openNode(tr.dataset.node));
    });
  }

  function updateOverviewKpisFromOverlay() {
    if (!liveProbeOverlay || !Array.isArray(liveProbeOverlay.nodes)) return;
    const nodes = liveProbeOverlay.nodes;
    let healthy = 0;
    let unhealthy = 0;
    for (const n of nodes) {
      const bad =
        n.ssh === "FAIL" ||
        n.proxy === "FAIL" ||
        n.accounting === "FAIL" ||
        n.ssh === "UNKNOWN" ||
        n.proxy === "UNKNOWN";
      if (bad) unhealthy += 1;
      else healthy += 1;
    }
    const kpis = $("#kpi-row");
    if (!kpis || !kpis.children.length) return;
    const labels = ["Nodes", "Active", "Healthy", "Unhealthy", "Last probe"];
    const values = [
      String(nodes.length),
      String(nodes.filter((n) => n.enabled !== false).length),
      String(healthy),
      String(unhealthy),
      liveProbeOverlay.controller_utc || "—",
    ];
    kpis.innerHTML = labels
      .map((label, i) => {
        const cls =
          label === "Healthy"
            ? values[i] !== "0"
              ? "ok"
              : ""
            : label === "Unhealthy"
              ? values[i] !== "0"
                ? "bad"
                : "ok"
              : "";
        return `<div class="kpi"><div class="label">${label}</div><div class="value ${cls}">${escapeHtml(
          values[i]
        )}</div></div>`;
      })
      .join("");
  }

  async function loadOverview() {
    const data = await api("/api/overview");
    $("#foot-version").textContent = `vcl-fleet ${data.version || ""}`;
    renderWarnings(data.warnings);
    renderWorkspaceStrip($("#workspace-strip"), data.workspace);
    updateLiveProbeStrip();

    if (!liveProbeOverlay) {
      const unhealthy = data.unhealthy || 0;
      $("#kpi-row").innerHTML = [
        ["Nodes", data.node_count],
        ["Active", data.active_node_count],
        ["Healthy", data.healthy, data.healthy ? "ok" : ""],
        ["Unhealthy", unhealthy, unhealthy ? "bad" : "ok"],
        ["Last probe", data.last_status_at || "—"],
      ]
        .map(
          ([label, value, cls]) =>
            `<div class="kpi"><div class="label">${label}</div><div class="value ${cls || ""}">${escapeHtml(
              value
            )}</div></div>`
        )
        .join("");
    } else {
      updateOverviewKpisFromOverlay();
    }

    const userRows = (data.top_users || [])
      .map(
        (r) =>
          `<tr class="clickable" data-user="${escapeHtml(r.user_tag || r.user_id || "")}">
            <td>${escapeHtml(r.user_tag || r.user_id || "?")}</td>
            <td>${escapeHtml(r.node)}</td>
            <td>${human(r.bytes)}</td>
          </tr>`
      )
      .join("");
    $("#top-users").innerHTML = userRows
      ? table(["User", "Node", "Bytes"], userRows)
      : `<p class="empty">No daily_usage yet. Run Sync (--full) first.</p>`;

    const hostRows = (data.top_hosts || [])
      .map(
        (r) =>
          `<tr>
            <td>${escapeHtml(r.destination_host || "?")}</td>
            <td>${escapeHtml(r.node)}</td>
            <td>${human(r.bytes)}</td>
          </tr>`
      )
      .join("");
    $("#top-hosts").innerHTML = hostRows
      ? table(["Host", "Node", "Bytes"], hostRows)
      : `<p class="empty">No destinations yet. Run Sync (--full) first.</p>`;

    $("#overview-warnings").innerHTML = (data.warnings || []).length
      ? `<ul>${(data.warnings || [])
          .map((w) => `<li>${escapeHtml(w.message)}</li>`)
          .join("")}</ul>`
      : `<p class="empty">No warnings in cache.</p>`;

    $("#top-users").querySelectorAll("tr.clickable").forEach((tr) => {
      tr.addEventListener("click", () => openUser(tr.dataset.user));
    });
  }

  async function loadNodes() {
    const data = await api("/api/nodes");
    renderNodesTable($("#nodes-table"), data);
  }

  async function loadUsers() {
    try {
      const users = await api("/api/users");
      const rows = (users.users || [])
        .map((u) => {
          const nodes = (u.nodes || []).map((n) => n.name).join(", ") || "—";
          return `<tr class="clickable" data-user="${escapeHtml(u.tag || "")}">
            <td>${escapeHtml(u.tag || "?")}</td>
            <td><code>${escapeHtml((u.user_id || "").slice(0, 8))}…</code></td>
            <td>${escapeHtml(nodes)}</td>
            <td>${escapeHtml(u.source || "cache")}</td>
          </tr>`;
        })
        .join("");
      $("#users-table").innerHTML =
        `<p class="hint">Source: ${escapeHtml(users.source || "cache")}. ${escapeHtml(
          users.note || ""
        )}</p>` +
        (rows
          ? table(["Tag", "user_id", "Nodes", "Source"], rows)
          : `<p class="empty">No users in cache. Sync (--full) or Refresh users.</p>`);
      $("#users-table").querySelectorAll("tr.clickable").forEach((tr) => {
        tr.addEventListener("click", () => openUser(tr.dataset.user));
      });
    } catch (err) {
      $("#users-table").innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  async function loadTraffic() {
    const kind = $("#traffic-kind").value || "users";
    const days = $("#traffic-days").value || "7";
    try {
      const data = await api(`/api/stats/top?kind=${encodeURIComponent(kind)}&days=${encodeURIComponent(days)}`);
      const rows = (data.rows || [])
        .map((r) => {
          if (kind === "users") {
            return `<tr>
              <td>${escapeHtml(r.user_tag || r.user_id || "?")}</td>
              <td>${escapeHtml(r.node)}</td>
              <td>${human(r.bytes)}</td>
              <td>${escapeHtml(r.connection_count)}</td>
            </tr>`;
          }
          if (kind === "nodes") {
            return `<tr>
              <td>${escapeHtml(r.node)}</td>
              <td>${human(r.bytes)}</td>
              <td>${escapeHtml(r.connection_count)}</td>
            </tr>`;
          }
          return `<tr>
            <td>${escapeHtml(r.destination_host || "?")}</td>
            <td>${escapeHtml(r.node)}</td>
            <td>${human(r.bytes)}</td>
            <td>${escapeHtml(r.connection_count)}</td>
          </tr>`;
        })
        .join("");
      const headers =
        kind === "users"
          ? ["User", "Node", "Bytes", "Conns"]
          : kind === "nodes"
            ? ["Node", "Bytes", "Conns"]
            : ["Host", "Node", "Bytes", "Conns"];
      $("#traffic-results").innerHTML = rows
        ? table(headers, rows)
        : `<p class="empty">No traffic in window. Run Sync (--full) first.</p>`;
    } catch (err) {
      $("#traffic-results").innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  async function loadOperations() {
    try {
      const data = await api("/api/operations");
      const rows = (data.rows || [])
        .map(
          (r) =>
            `<tr>
              <td>${escapeHtml(r.at || "—")}</td>
              <td>${escapeHtml(r.operation || "?")}</td>
              <td>${escapeHtml(r.state || "—")}</td>
              <td>${escapeHtml(String(r.exit_code))}</td>
              <td>${escapeHtml(r.target || "")}</td>
            </tr>`
        )
        .join("");
      $("#operations-table").innerHTML = rows
        ? table(["Time", "Operation", "State", "Exit", "Target"], rows)
        : `<p class="empty">No operations recorded yet. Probe, Verify, Sync, or Refresh users.</p>`;
    } catch (err) {
      $("#operations-table").innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  function openDrawer(title, html) {
    $("#drawer-title").textContent = title;
    $("#drawer-body").innerHTML = html;
    $("#drawer").hidden = false;
    $("#drawer-backdrop").hidden = false;
  }

  function closeDrawer() {
    $("#drawer").hidden = true;
    $("#drawer-backdrop").hidden = true;
  }

  async function openNode(name) {
    try {
      const data = await api(`/api/nodes/${encodeURIComponent(name)}`);
      const n = data.node || {};
      let probe = data.probe || {};
      if (liveProbeOverlay && Array.isArray(liveProbeOverlay.nodes)) {
        const live = liveProbeOverlay.nodes.find((x) => x.name === name);
        if (live) probe = { ...probe, ...live };
      }
      const c = data.cursor || {};
      const inst = (data.instances || [])
        .map(
          (i) =>
            `<tr><td><code>${escapeHtml(i.instance_id)}</code></td><td>${escapeHtml(
              i.status
            )}</td><td>${escapeHtml(i.endpoint || i.ssh_host || "—")}</td><td>${escapeHtml(
              i.started_at
            )}</td><td>${escapeHtml(i.retired_at || "—")}</td></tr>`
        )
        .join("");
      openDrawer(
        `Node ${n.name}`,
        `
        <p class="hint">${escapeHtml(data.secrets_note || "")}</p>
        <pre class="block">node_id: ${escapeHtml(n.node_id)}
status: ${escapeHtml(n.status)}
endpoint: ${escapeHtml(n.ssh_user)}@${escapeHtml(n.ssh_host)}:${escapeHtml(n.ssh_port)}
instance_id: ${escapeHtml(probe.instance_id || c.instance_id || "—")}
ssh/proxy/accounting: ${escapeHtml(probe.ssh || "-")} / ${escapeHtml(probe.proxy || "-")} / ${escapeHtml(
          probe.accounting || "-"
        )}
version: ${escapeHtml(probe.vincula_version || "—")}
last_sync: ${escapeHtml(c.last_sync_at || "—")} (${escapeHtml(c.status || "—")})
cursor: ${escapeHtml(c.last_event_id == null ? "—" : c.last_event_id)}</pre>
        <h3>Instances</h3>
        ${
          inst
            ? table(["instance_id", "status", "endpoint", "started", "retired"], inst)
            : `<p class="empty">No instance_history rows.</p>`
        }
        <p class="hint"><button type="button" class="linkish" id="audit-from-node">Open Audit for this node</button></p>
        `
      );
      const btn = $("#audit-from-node");
      if (btn) {
        btn.addEventListener("click", () => {
          closeDrawer();
          showPage("audit");
          $("#audit-node").value = n.name;
          const w = defaultWindow();
          if (!$("#audit-from").value) $("#audit-from").value = w.from;
          if (!$("#audit-to").value) $("#audit-to").value = w.to;
        });
      }
    } catch (err) {
      toast(err.message);
    }
  }

  async function openUser(tag) {
    if (!tag) return;
    try {
      const data = await api(`/api/users/${encodeURIComponent(tag)}`);
      const u = data.user || {};
      const nodes = (u.nodes || [])
        .map(
          (n) =>
            `<tr><td>${escapeHtml(n.name)}</td><td>${escapeHtml(
              String(n.enabled)
            )}</td><td>${escapeHtml(n.status || "—")}</td><td>${escapeHtml(
              n.has_active_credential === true
                ? "yes"
                : n.has_active_credential === false
                  ? "no"
                  : "—"
            )}</td></tr>`
        )
        .join("");
      const usage = (data.recent_usage || [])
        .map(
          (r) =>
            `<tr><td>${escapeHtml(r.node)}</td><td>${human(r.bytes)}</td><td>${escapeHtml(
              r.connection_count
            )}</td></tr>`
        )
        .join("");
      openDrawer(
        `User ${u.tag || tag}`,
        `
        <p class="hint">${escapeHtml(data.secrets_note || "")}</p>
        <pre class="block">tag: ${escapeHtml(u.tag || tag)}
user_id: ${escapeHtml(u.user_id || "—")}
display_name: ${escapeHtml(u.display_name || "—")}
department: ${escapeHtml(u.department || "—")}
source: ${escapeHtml(u.source || "—")}</pre>
        <h3>Assigned nodes</h3>
        ${
          nodes
            ? table(["node", "enabled", "status", "active credential"], nodes)
            : `<p class="empty">No node assignment in cache.</p>`
        }
        <h3>Recent usage (7d, approximate)</h3>
        ${usage ? table(["node", "bytes", "conns"], usage) : `<p class="empty">No usage.</p>`}
        <p class="hint"><button type="button" class="linkish" id="audit-from-user">Open Audit for this user</button></p>
        `
      );
      const btn = $("#audit-from-user");
      if (btn) {
        btn.addEventListener("click", () => {
          closeDrawer();
          showPage("audit");
          $("#audit-user").value = u.tag || tag;
          const w = defaultWindow();
          $("#audit-from").value = w.from;
          $("#audit-to").value = w.to;
        });
      }
    } catch (err) {
      toast(err.message);
    }
  }

  async function runAudit(ev) {
    ev.preventDefault();
    const params = new URLSearchParams({
      user: $("#audit-user").value.trim(),
      from: $("#audit-from").value.trim(),
      to: $("#audit-to").value.trim(),
    });
    const node = $("#audit-node").value.trim();
    const dest = $("#audit-dest").value.trim();
    if (node) params.set("node", node);
    if (dest) params.set("destination", dest);
    try {
      const data = await api(`/api/audit?${params.toString()}`);
      const rows = (data.rows || [])
        .map(
          (r) =>
            `<tr>
              <td>${escapeHtml(r.time)}</td>
              <td>${escapeHtml(r.node)}</td>
              <td>${escapeHtml(r.destination)}</td>
              <td>${escapeHtml(r.upload_human)} / ${escapeHtml(r.download_human)}</td>
              <td>${escapeHtml(r.traffic_human)}</td>
            </tr>`
        )
        .join("");
      $("#audit-results").innerHTML = rows
        ? table(["time", "node", "dest", "up / down", "total"], rows) +
          (data.truncated
            ? `<p class="hint">Truncated at ${escapeHtml(
                String(data.limit)
              )} rows. Narrow the window or use next_cursor / CLI.</p>`
            : "")
        : `<p class="empty">${escapeHtml(data.empty_hint || "No connections in window.")}</p>`;
    } catch (err) {
      $("#audit-results").innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  async function postJson(path, body) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  async function runProbe() {
    try {
      toast("Running live probe…");
      const data = await postJson("/api/refresh/probe", {});
      liveProbeOverlay = data.result || null;
      toast(`${data.operation} exit ${data.exit_code}`);
      updateLiveProbeStrip();
      updateOverviewKpisFromOverlay();
      await loadNodes();
      const active = $(".page.active");
      if (active && active.id === "page-overview") {
        await loadOverview();
      }
    } catch (err) {
      toast(err.message);
    }
  }

  async function runVerify() {
    try {
      toast("Running verify…");
      liveProbeOverlay = null;
      updateLiveProbeStrip();
      const data = await postJson("/api/refresh/verify", {});
      toast(`${data.operation} exit ${data.exit_code}`);
      await Promise.all([loadOverview(), loadNodes(), loadOperations()]);
    } catch (err) {
      toast(err.message);
    }
  }

  async function doSync() {
    if (
      !window.confirm(
        "Run sync --full now?\n\nThis pulls identity + health + users + audit into local fleet.db via SSH.\nReseed remains CLI-only (vcl-fleet sync --reseed NAME)."
      )
    ) {
      return;
    }
    try {
      toast("Sync --full…");
      liveProbeOverlay = null;
      updateLiveProbeStrip();
      const data = await postJson("/api/sync", {});
      const label = data.operation || "sync_full";
      if (data.ok) {
        toast(`${label} exit ${data.exit_code}`);
      } else {
        toast(`${label} PARTIAL/FAIL exit ${data.exit_code}`);
      }
      await Promise.all([loadOverview(), loadNodes(), loadUsers(), loadOperations()]);
    } catch (err) {
      toast(err.message);
    }
  }

  async function openRecipes() {
    try {
      const data = await api("/api/recipes");
      $("#recipes-body").innerHTML = (data.recipes || [])
        .map(
          (r) =>
            `<div class="recipe">
              <strong>${escapeHtml(r.title)}</strong>
              <code>${escapeHtml(r.command)}</code>
              <button type="button" class="btn copy-btn" data-cmd="${escapeHtml(
                r.command
              )}">Copy</button>
            </div>`
        )
        .join("");
      $("#recipes").hidden = false;
      $("#drawer-backdrop").hidden = false;
      $$(".copy-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(btn.dataset.cmd);
            toast("Copied");
          } catch (_) {
            toast("Copy failed — select the command manually");
          }
        });
      });
    } catch (err) {
      toast(err.message);
    }
  }

  function closeRecipes() {
    $("#recipes").hidden = true;
    if ($("#drawer").hidden) $("#drawer-backdrop").hidden = true;
  }

  function wire() {
    $$(".tab").forEach((t) =>
      t.addEventListener("click", () => {
        showPage(t.dataset.page);
        const page = t.dataset.page;
        if (page === "overview") loadOverview();
        if (page === "nodes") loadNodes();
        if (page === "users") loadUsers();
        if (page === "traffic") loadTraffic();
        if (page === "operations") loadOperations();
      })
    );
    $("#goto-nodes").addEventListener("click", () => {
      showPage("nodes");
      loadNodes();
    });
    $("#goto-audit").addEventListener("click", () => showPage("audit"));
    $("#goto-operations").addEventListener("click", () => {
      showPage("operations");
      loadOperations();
    });
    $("#audit-form").addEventListener("submit", runAudit);
    $("#traffic-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      loadTraffic();
    });
    $("#btn-probe").addEventListener("click", runProbe);
    $("#btn-verify").addEventListener("click", runVerify);
    $("#btn-sync").addEventListener("click", doSync);
    $("#btn-recipes").addEventListener("click", openRecipes);
    $("#recipes-close").addEventListener("click", closeRecipes);
    $("#drawer-close").addEventListener("click", closeDrawer);
    $("#drawer-backdrop").addEventListener("click", () => {
      closeDrawer();
      closeRecipes();
    });
    $("#btn-refresh-users").addEventListener("click", async () => {
      try {
        toast("Refreshing users over SSH…");
        await postJson("/api/refresh/users", {});
        toast("Users cache updated");
        await Promise.all([loadUsers(), loadOperations()]);
      } catch (err) {
        toast(err.message);
      }
    });
    const w = defaultWindow();
    $("#audit-from").placeholder = w.from;
    $("#audit-to").placeholder = w.to;
  }

  wire();
  loadOverview().catch((err) => toast(err.message));
  loadNodes().catch(() => {});
})();
