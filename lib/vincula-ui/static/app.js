/* Vincula Local Audit UI v2 — stdlib static JS (no build). */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const STATE_CLASS = new Set(["OK", "STALE", "FAIL", "UNKNOWN", "WARN", "-", "DEGRADED", "EMPTY"]);
  const LEVEL_CLASS = new Set(["red", "amber"]);
  const TOKEN_HEADER = "X-Vincula-UI-Token";
  const SSH_HINT = "This action contacts remote nodes over SSH.";

  /** Live probe payload from POST /api/refresh/probe (does not write last-status). */
  let liveProbeOverlay = null;
  /** Command Builder operations from GET /api/command-builder */
  let commandBuilderOps = [];

  /** Shared gate for remote SSH actions (Probe / Verify / Sync / Refresh users). */
  function confirmRemoteSsh(detail) {
    return window.confirm(`${SSH_HINT}\n\n${detail}`);
  }

  function uiToken() {
    const meta = document.querySelector('meta[name="vcl-ui-token"]');
    return (meta && meta.getAttribute("content")) || "";
  }

  /** Operations table time cell — prefers ``time``, then finished/started. */
  function operationTimeCell(r) {
    const t = r && (r.time || r.finished_at || r.started_at);
    return t ? String(t) : "—";
  }

  function truncateField(s, maxLen) {
    const t = String(s == null ? "" : s);
    const max = maxLen || 40;
    if (t.length <= max) return escapeHtml(t);
    return escapeHtml(t.slice(0, Math.max(1, max - 1))) + "…";
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

  function formatCacheAge(seconds) {
    if (seconds == null || seconds === "") return "—";
    const s = Number(seconds);
    if (!Number.isFinite(s)) return "—";
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  function nodeHealth(n) {
    if (n && n.health && n.health !== "—") return n.health;
    if (!n) return "—";
    if (n.ssh === "FAIL" || n.proxy === "FAIL" || n.accounting === "FAIL") return "FAIL";
    return n.ssh || n.proxy || n.accounting || "—";
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
        "Workspace: <strong>absent</strong> — run <code>vcl-fleet workspace init</code>, then <code>node adopt</code> / <code>node provision</code>.";
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
        health: nodeHealth({ ...prev, ...p }),
        last_sync_at: prev.last_sync_at || p.last_sync_at,
        user_count: prev.user_count,
        traffic_today_human: prev.traffic_today_human,
        endpoint: prev.endpoint || p.endpoint,
        version: p.vincula_version || prev.version,
      };
    }
    const order = base.map((n) => n.name).filter(Boolean);
    const extra = Object.keys(byName).filter((k) => !order.includes(k));
    return order.concat(extra).map((name) => byName[name]);
  }

  function countHealthy(nodes) {
    let healthy = 0;
    let offline = 0;
    for (const n of nodes || []) {
      const h = nodeHealth(n);
      if (h === "FAIL" || h === "UNKNOWN") offline += 1;
      else if (h === "OK" || h === "STALE" || h === "-") healthy += 1;
      else offline += 1;
    }
    return { healthy, offline };
  }

  function renderKpiRow(items) {
    const kpis = $("#kpi-row");
    if (!kpis) return;
    kpis.innerHTML = items
      .map(([label, value, cls]) => {
        const valueHtml =
          label === "Fleet Health" ? statePill(value) : escapeHtml(String(value ?? "—"));
        return `<div class="kpi"><div class="label">${escapeHtml(label)}</div><div class="value ${cls || ""}">${valueHtml}</div></div>`;
      })
      .join("");
  }

  function updateOverviewKpisFromOverlay(cacheData) {
    if (!liveProbeOverlay || !Array.isArray(liveProbeOverlay.nodes)) return;
    const nodes = liveProbeOverlay.nodes;
    const { healthy, offline } = countHealthy(nodes);
    const fleetHealth =
      offline === 0 && nodes.length ? "OK" : nodes.length ? "DEGRADED" : "EMPTY";
    const tt = (cacheData && cacheData.traffic_today) || {};
    renderKpiRow([
      ["Fleet Health", fleetHealth, fleetHealth === "OK" ? "ok" : fleetHealth === "EMPTY" ? "" : "bad"],
      ["Nodes", String(nodes.length)],
      ["Healthy", String(healthy), healthy ? "ok" : ""],
      ["Offline", String(offline), offline ? "bad" : "ok"],
      ["Users", cacheData ? String(cacheData.user_count ?? "—") : "—"],
      ["Conns Today", cacheData ? String(cacheData.active_connections_today ?? "—") : "—"],
      [
        "Traffic Today",
        tt.bytes_human
          ? `${tt.bytes_human} (↑${tt.upload_human || "0 B"} ↓${tt.download_human || "0 B"})`
          : "—",
      ],
      ["Last Sync", (cacheData && cacheData.last_sync_at) || "—"],
      [
        "Cache Age",
        formatCacheAge(cacheData && cacheData.cache_age_seconds),
      ],
    ]);
  }

  function renderOverviewKpis(data) {
    const unhealthy = data.offline != null ? data.offline : data.unhealthy || 0;
    const tt = data.traffic_today || {};
    renderKpiRow([
      [
        "Fleet Health",
        data.fleet_health || "—",
        data.fleet_health === "OK" ? "ok" : data.fleet_health === "EMPTY" ? "" : "bad",
      ],
      ["Nodes", data.node_count],
      ["Healthy", data.healthy, data.healthy ? "ok" : ""],
      ["Offline", unhealthy, unhealthy ? "bad" : "ok"],
      ["Users", data.user_count],
      ["Conns Today", data.active_connections_today],
      [
        "Traffic Today",
        tt.bytes_human
          ? `${tt.bytes_human} (↑${tt.upload_human || "0 B"} ↓${tt.download_human || "0 B"})`
          : "—",
      ],
      ["Last Sync", data.last_sync_at || "—"],
      ["Cache Age", formatCacheAge(data.cache_age_seconds)],
    ]);
  }

  function renderTrafficTrendTable(container, trend, emptyMsg) {
    if (!container) return;
    const rows = (trend || [])
      .map(
        (r) =>
          `<tr>
            <td>${escapeHtml(r.date || "—")}</td>
            <td>${escapeHtml(r.bytes_human || human(r.bytes))}</td>
            <td>${human(r.upload_bytes)}</td>
            <td>${human(r.download_bytes)}</td>
            <td>${escapeHtml(String(r.connection_count ?? "—"))}</td>
          </tr>`
      )
      .join("");
    container.innerHTML = rows
      ? table(["Date", "Total", "Upload", "Download", "Conns"], rows)
      : `<p class="empty">${escapeHtml(emptyMsg)}</p>`;
  }

  function renderNodeHealthMini(container, rows, emptyMsg) {
    if (!container) return;
    const merged = mergeLiveNodes(rows || []);
    const html = merged
      .map(
        (n) =>
          `<tr class="clickable${liveProbeOverlay ? " live-row" : ""}" data-node="${escapeHtml(n.name)}">
            <td>${escapeHtml(n.name)}${liveProbeOverlay ? ' <span class="muted">live</span>' : ""}</td>
            <td>${statePill(nodeHealth(n))}</td>
            <td>${escapeHtml(n.version || "—")}</td>
            <td>${escapeHtml(n.last_sync_at || "—")}</td>
          </tr>`
      )
      .join("");
    container.innerHTML = html
      ? table(["Node", "Health", "Version", "Last sync"], html)
      : `<p class="empty">${escapeHtml(emptyMsg)}</p>`;
    container.querySelectorAll("tr.clickable").forEach((tr) => {
      tr.addEventListener("click", () => openNode(tr.dataset.node));
    });
  }

  function renderRecentProblems(container, problems) {
    if (!container) return;
    const items = problems || [];
    container.innerHTML = items.length
      ? `<ul>${items
          .map(
            (w) =>
              `<li><span class="chip ${warnLevel(w.level)}">${escapeHtml(
                w.message || w.code || "?"
              )}</span></li>`
          )
          .join("")}</ul>`
      : `<p class="empty">No recent problems in cache.</p>`;
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
            <td>${statePill(nodeHealth(n))}</td>
            <td>${escapeHtml(n.version || "—")}</td>
            <td>${escapeHtml(n.last_sync_at || "—")}</td>
            <td>${escapeHtml(String(n.user_count ?? "—"))}</td>
            <td>${escapeHtml(n.traffic_today_human || human(n.traffic_today_bytes))}</td>
            <td><code>${escapeHtml(n.endpoint || "—")}</code></td>
          </tr>`
      )
      .join("");
    container.innerHTML = rows
      ? table(
          ["NODE", "HEALTH", "VERSION", "LAST SYNC", "USERS", "TRAFFIC TODAY", "ENDPOINT"],
          rows
        )
      : `<p class="empty">No nodes in fleet.json. Run <code>vcl-fleet workspace init</code> then <code>node adopt</code> / <code>node provision</code>.</p>`;
    container.querySelectorAll("tr.clickable").forEach((tr) => {
      tr.addEventListener("click", () => openNode(tr.dataset.node));
    });
  }

  async function loadOverview() {
    const data = await api("/api/overview");
    $("#foot-version").textContent = `vcl-fleet ${data.version || ""}`;
    renderWarnings(data.warnings);
    renderWorkspaceStrip($("#workspace-strip"), data.workspace);
    updateLiveProbeStrip();

    if (liveProbeOverlay) {
      updateOverviewKpisFromOverlay(data);
    } else {
      renderOverviewKpis(data);
    }

    renderTrafficTrendTable(
      $("#traffic-trend"),
      data.traffic_trend,
      "No traffic trend yet. Run Sync (--full) first."
    );
    renderNodeHealthMini(
      $("#node-health-table"),
      data.node_health,
      "No nodes yet. Run workspace init then node adopt / node provision."
    );
    renderRecentProblems($("#recent-problems"), data.recent_problems);

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
          const nodes = u.node_names || (u.nodes || []).map((n) => n.name).join(", ") || "—";
          return `<tr class="clickable" data-user="${escapeHtml(u.tag || "")}">
            <td>${escapeHtml(u.tag || "?")}</td>
            <td>${escapeHtml(u.department || "—")}</td>
            <td>${escapeHtml(nodes)}</td>
            <td>${escapeHtml(u.enabled_state || "—")}</td>
            <td>${escapeHtml(u.today_human || human(u.today_bytes))}</td>
            <td>${escapeHtml(u.bytes_30d_human || human(u.bytes_30d))}</td>
          </tr>`;
        })
        .join("");
      $("#users-table").innerHTML =
        `<p class="hint">Source: ${escapeHtml(users.source || "cache")}. ${escapeHtml(
          users.note || ""
        )}</p>` +
        (rows
          ? table(["USER", "DEPARTMENT", "NODES", "ENABLED STATE", "TODAY", "30D"], rows)
          : `<p class="empty">No users in cache. Sync (--full) or Refresh users.</p>`);
      $("#users-table").querySelectorAll("tr.clickable").forEach((tr) => {
        tr.addEventListener("click", () => openUser(tr.dataset.user));
      });
    } catch (err) {
      $("#users-table").innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  function trafficRowCells(r, kind) {
    const up = r.upload_human || human(r.upload_bytes);
    const down = r.download_human || human(r.download_bytes);
    const total = r.bytes_human || human(r.bytes);
    const conns = escapeHtml(String(r.connection_count ?? "—"));
    if (kind === "users") {
      return `<td>${escapeHtml(r.user_tag || r.user_id || "?")}</td>
        <td>${escapeHtml(r.node)}</td>
        <td>${escapeHtml(up)}</td>
        <td>${escapeHtml(down)}</td>
        <td>${escapeHtml(total)}</td>
        <td>${conns}</td>`;
    }
    if (kind === "nodes") {
      return `<td>${escapeHtml(r.node)}</td>
        <td>${escapeHtml(up)}</td>
        <td>${escapeHtml(down)}</td>
        <td>${escapeHtml(total)}</td>
        <td>${conns}</td>`;
    }
    return `<td>${escapeHtml(r.destination_host || "?")}</td>
      <td>${escapeHtml(r.node)}</td>
      <td>${escapeHtml(up)}</td>
      <td>${escapeHtml(down)}</td>
      <td>${escapeHtml(total)}</td>
      <td>${conns}</td>`;
  }

  function trafficHeaders(kind) {
    if (kind === "users") {
      return ["User", "Node", "Upload", "Download", "Total", "Conns"];
    }
    if (kind === "nodes") {
      return ["Node", "Upload", "Download", "Total", "Conns"];
    }
    return ["Host", "Node", "Upload", "Download", "Total", "Conns"];
  }

  async function loadTraffic() {
    const kind = $("#traffic-kind").value || "users";
    const days = $("#traffic-days").value || "7";
    const params = new URLSearchParams({
      kind,
      days,
    });
    const node = $("#traffic-node").value.trim();
    const user = $("#traffic-user").value.trim();
    const department = $("#traffic-department").value.trim();
    const destination = $("#traffic-destination").value.trim();
    if (node) params.set("node", node);
    if (user) params.set("user", user);
    if (department) params.set("department", department);
    if (destination) params.set("destination", destination);
    try {
      const data = await api(`/api/stats/top?${params.toString()}`);
      const totals = data.totals || {};
      const totalsEl = $("#traffic-totals");
      totalsEl.hidden = false;
      totalsEl.innerHTML = `Totals (${escapeHtml(String(data.days || days))}d): ↑ ${escapeHtml(
        totals.upload_human || human(totals.upload_bytes)
      )} · ↓ ${escapeHtml(totals.download_human || human(totals.download_bytes))} · ${escapeHtml(
        totals.bytes_human || human(totals.bytes)
      )}`;

      const trendPanel = $("#traffic-trend-panel");
      trendPanel.hidden = false;
      renderTrafficTrendTable(
        trendPanel,
        data.trend,
        "No trend data in window."
      );

      const rows = (data.rows || [])
        .map((r) => `<tr>${trafficRowCells(r, kind)}</tr>`)
        .join("");
      $("#traffic-results").innerHTML = rows
        ? table(trafficHeaders(kind), rows)
        : `<p class="empty">No traffic in window. Run Sync (--full) first.</p>`;
    } catch (err) {
      $("#traffic-totals").hidden = true;
      $("#traffic-trend-panel").hidden = true;
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
              <td>${escapeHtml(operationTimeCell(r))}</td>
              <td>${escapeHtml(r.operation || "?")}</td>
              <td>${truncateField(r.target || "", 36)}</td>
              <td>${escapeHtml(r.state || "—")}</td>
              <td>${escapeHtml(r.ok === false ? "FAIL" : r.ok === true ? "OK" : String(r.exit_code ?? "—"))}</td>
              <td>${escapeHtml(r.controller_version || "—")}</td>
              <td title="${escapeHtml(r.detail || "")}">${truncateField(r.detail || "—", 48)}</td>
            </tr>`
        )
        .join("");
      $("#operations-table").innerHTML = rows
        ? table(
            ["TIME", "OPERATION", "TARGET", "STATE", "RESULT", "CTRL", "DETAIL"],
            rows
          )
        : `<p class="empty">No operations recorded yet. Probe, Verify, Sync, or CLI mutations.</p>`;
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
    if ($("#recipes").hidden && $("#command-builder").hidden) {
      $("#drawer-backdrop").hidden = true;
    }
  }

  function renderLastOperations(ops) {
    const rows = (ops || [])
      .map(
        (r) =>
          `<tr>
            <td>${escapeHtml(operationTimeCell(r))}</td>
            <td>${escapeHtml(r.operation || "?")}</td>
            <td>${escapeHtml(r.target || "")}</td>
            <td>${escapeHtml(r.state || "—")}</td>
            <td>${escapeHtml(String(r.exit_code ?? "—"))}</td>
          </tr>`
      )
      .join("");
    return rows
      ? table(["Time", "Operation", "Target", "State", "Exit"], rows)
      : `<p class="empty">No operations recorded for this node.</p>`;
  }

  function renderNodeUsers(users) {
    const rows = (users || [])
      .map(
        (u) =>
          `<tr class="clickable" data-user="${escapeHtml(u.tag || "")}">
            <td>${escapeHtml(u.tag || "?")}</td>
            <td>${escapeHtml(u.department || "—")}</td>
            <td>${escapeHtml(String(u.enabled))}</td>
            <td>${escapeHtml(u.status || "—")}</td>
          </tr>`
      )
      .join("");
    return rows
      ? table(["User", "Department", "Enabled", "Status"], rows)
      : `<p class="empty">No users on this node in cache.</p>`;
  }

  function renderInstanceHistory(instances) {
    const rows = (instances || [])
      .map((inst) => {
        const status = String(inst.status || "—");
        const current = status === "active" ? " current" : "";
        const ended = inst.retired_at || inst.ended_at || "—";
        const endpoint = inst.endpoint || inst.ssh_host || "—";
        return `<tr class="${status === "active" ? "current-instance" : ""}">
            <td title="${escapeHtml(inst.instance_id || "")}">${truncateField(
          inst.instance_id || "—",
          20
        )}${current ? ' <span class="muted">(current)</span>' : ""}</td>
            <td>${escapeHtml(inst.started_at || "—")}</td>
            <td>${escapeHtml(ended)}</td>
            <td>${escapeHtml(status)}</td>
            <td title="${escapeHtml(endpoint)}">${truncateField(endpoint, 36)}</td>
          </tr>`;
      })
      .join("");
    return rows
      ? table(["instance_id", "started_at", "ended_at", "status", "endpoint"], rows)
      : `<p class="empty">No instance history in cache.</p>`;
  }

  function renderNodeRecentUsage(usage) {
    const rows = (usage || [])
      .map((r) => {
        const user = r.user_tag || r.user_id || "—";
        const host = r.destination_host || "—";
        return `<tr>
            <td title="${escapeHtml(user)}">${truncateField(user, 24)}</td>
            <td title="${escapeHtml(host)}">${truncateField(host, 36)}</td>
            <td>${human(r.bytes)}</td>
            <td>${escapeHtml(String(r.connection_count ?? "—"))}</td>
          </tr>`;
      })
      .join("");
    return rows
      ? table(["user", "destination", "bytes", "conns"], rows)
      : `<p class="empty">No recent usage (7d) in cache. Run Sync (--full) first.</p>`;
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
      const tt = data.traffic_today || {};
      openDrawer(
        `Node ${n.name}`,
        `
        <p class="hint">${escapeHtml(data.secrets_note || "")}</p>
        <pre class="block">node_id: ${escapeHtml(n.node_id)}
status: ${escapeHtml(n.status)}
endpoint: ${escapeHtml(n.endpoint || "—")}
health: ${escapeHtml(nodeHealth(probe))} (ssh ${escapeHtml(probe.ssh || "-")} / proxy ${escapeHtml(
          probe.proxy || "-"
        )} / accounting ${escapeHtml(probe.accounting || "-")})
version: ${escapeHtml(probe.vincula_version || "—")}
traffic today: ${escapeHtml(tt.bytes_human || human(tt.bytes))}</pre>
        <h3>Users</h3>
        <div id="node-drawer-users">${renderNodeUsers(data.users)}</div>
        <h3>Instance History</h3>
        ${renderInstanceHistory(data.instances)}
        <h3>Recent usage (7d, approximate)</h3>
        ${renderNodeRecentUsage(data.recent_usage)}
        <h3>Last operations</h3>
        ${renderLastOperations(data.last_operations)}
        <p class="hint"><button type="button" class="linkish" id="audit-from-node">Open Audit for this node</button></p>
        `
      );
      $("#node-drawer-users").querySelectorAll("tr.clickable").forEach((tr) => {
        tr.addEventListener("click", () => openUser(tr.dataset.user));
      });
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
      const usage = (data.recent_usage || u.recent_usage || [])
        .map(
          (r) =>
            `<tr><td>${escapeHtml(r.node)}</td><td>${human(r.bytes)}</td><td>${escapeHtml(
              r.connection_count
            )}</td></tr>`
        )
        .join("");
      const destRows = (data.destinations || [])
        .map(
          (r) =>
            `<tr>
              <td title="${escapeHtml(r.destination_host || "")}">${truncateField(
                r.destination_host || "—",
                40
              )}</td>
              <td>${escapeHtml(r.bytes_human || human(r.bytes))}</td>
              <td>${escapeHtml(String(r.connection_count ?? "—"))}</td>
            </tr>`
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
enabled state: ${escapeHtml(u.enabled_state || "—")}
source: ${escapeHtml(u.source || "—")}</pre>
        <h3>Per-node deployment</h3>
        ${
          nodes
            ? table(["node", "enabled", "status", "active credential"], nodes)
            : `<p class="empty">No node assignment in cache.</p>`
        }
        <h3>Recent usage (7d, approximate)</h3>
        ${usage ? table(["node", "bytes", "conns"], usage) : `<p class="empty">No usage.</p>`}
        <h3>Top destinations (7d)</h3>
        ${
          destRows
            ? table(["host", "bytes", "conns"], destRows)
            : `<p class="empty">No destinations yet. Run Sync (--full) first.</p>`
        }
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
    const destIp = $("#audit-dest-ip").value.trim();
    const port = $("#audit-port").value.trim();
    const network = $("#audit-network").value.trim();
    if (node) params.set("node", node);
    if (dest) params.set("destination", dest);
    if (destIp) params.set("destination_ip", destIp);
    if (port) params.set("port", port);
    if (network) params.set("network", network);
    try {
      const data = await api(`/api/audit?${params.toString()}`);
      const rows = (data.rows || [])
        .map(
          (r) =>
            `<tr>
              <td>${escapeHtml(r.time)}</td>
              <td>${escapeHtml(r.node)}</td>
              <td>${escapeHtml(r.destination)}</td>
              <td>${escapeHtml(r.destination_ip || "—")}</td>
              <td>${escapeHtml(r.destination_port != null ? String(r.destination_port) : "—")}</td>
              <td>${escapeHtml(r.network || "—")}</td>
              <td>${escapeHtml(r.upload_human)} / ${escapeHtml(r.download_human)}</td>
              <td>${escapeHtml(r.traffic_human)}</td>
            </tr>`
        )
        .join("");
      $("#audit-results").innerHTML = rows
        ? table(
            ["time", "node", "dest", "dest IP", "port", "network", "up / down", "total"],
            rows
          ) +
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
    if (!confirmRemoteSsh("Run live probe now?")) {
      return;
    }
    try {
      toast("Running live probe…");
      const data = await postJson("/api/refresh/probe", {});
      liveProbeOverlay = data.result || null;
      toast(`${data.operation} exit ${data.exit_code}`);
      updateLiveProbeStrip();
      await loadNodes();
      const active = $(".page.active");
      if (active && active.id === "page-overview") {
        await loadOverview();
      } else {
        const overviewData = await api("/api/overview");
        updateOverviewKpisFromOverlay(overviewData);
      }
    } catch (err) {
      toast(err.message);
    }
  }

  async function runVerify() {
    if (!confirmRemoteSsh("Run verify now?")) {
      return;
    }
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
      !confirmRemoteSsh(
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
      $$("#recipes-body .copy-btn").forEach((btn) => {
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
    if ($("#drawer").hidden && $("#command-builder").hidden) {
      $("#drawer-backdrop").hidden = true;
    }
  }

  function renderCommandBuilderFields(opId) {
    const fieldsEl = $("#cb-fields");
    const op = commandBuilderOps.find((o) => o.id === opId);
    if (!op || !fieldsEl) return;
    fieldsEl.innerHTML = (op.fields || [])
      .map(
        (f) =>
          `<label>${escapeHtml(f.label || f.name)}${f.required ? " *" : ""}
            <input name="${escapeHtml(f.name)}" data-field="${escapeHtml(f.name)}" ${
              f.required ? "required" : ""
            } autocomplete="off" />
          </label>`
      )
      .join("");
    $("#cb-output-wrap").hidden = true;
    $("#cb-output").textContent = "";
  }

  async function ensureCommandBuilderMeta() {
    if (commandBuilderOps.length) return;
    const data = await api("/api/command-builder");
    commandBuilderOps = data.operations || [];
    const sel = $("#cb-operation");
    sel.innerHTML = commandBuilderOps
      .map((o) => `<option value="${escapeHtml(o.id)}">${escapeHtml(o.title)}</option>`)
      .join("");
    if (commandBuilderOps.length) {
      renderCommandBuilderFields(commandBuilderOps[0].id);
    }
  }

  async function openCommandBuilder() {
    try {
      await ensureCommandBuilderMeta();
      $("#command-builder").hidden = false;
      $("#drawer-backdrop").hidden = false;
    } catch (err) {
      toast(err.message);
    }
  }

  function closeCommandBuilder() {
    $("#command-builder").hidden = true;
    if ($("#drawer").hidden && $("#recipes").hidden) {
      $("#drawer-backdrop").hidden = true;
    }
  }

  async function generateCommand() {
    const opId = $("#cb-operation").value;
    const fields = {};
    $$("#cb-fields [data-field]").forEach((input) => {
      fields[input.dataset.field] = input.value.trim();
    });
    try {
      const data = await postJson("/api/command-builder", {
        operation: opId,
        fields,
      });
      $("#cb-output").textContent = data.command || "";
      $("#cb-output-wrap").hidden = !data.command;
    } catch (err) {
      toast(err.message);
    }
  }

  async function copyGeneratedCommand() {
    const text = $("#cb-output").textContent;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied");
    } catch (_) {
      toast("Copy failed — select the command manually");
    }
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
    $("#btn-command-builder").addEventListener("click", openCommandBuilder);
    $("#recipes-close").addEventListener("click", closeRecipes);
    $("#command-builder-close").addEventListener("click", closeCommandBuilder);
    $("#cb-operation").addEventListener("change", (ev) => {
      renderCommandBuilderFields(ev.target.value);
    });
    $("#cb-generate").addEventListener("click", generateCommand);
    $("#cb-copy").addEventListener("click", copyGeneratedCommand);
    $("#drawer-close").addEventListener("click", closeDrawer);
    $("#drawer-backdrop").addEventListener("click", () => {
      closeDrawer();
      closeRecipes();
      closeCommandBuilder();
    });
    $("#btn-refresh-users").addEventListener("click", async () => {
      if (!confirmRemoteSsh("Refresh users from remote nodes now?")) {
        return;
      }
      try {
        toast("Refreshing users…");
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
