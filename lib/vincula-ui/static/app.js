/* Vincula Local Audit UI — stdlib static JS (no build). */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const STATE_CLASS = new Set(["OK", "STALE", "FAIL", "UNKNOWN", "WARN", "-"]);
  const LEVEL_CLASS = new Set(["red", "amber"]);
  const TOKEN_HEADER = "X-Vincula-UI-Token";

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

  async function loadOverview() {
    const data = await api("/api/overview");
    $("#foot-version").textContent = `vcl-fleet ${data.version || ""}`;
    renderWarnings(data.warnings);
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
      : `<p class="empty">No daily_usage yet. Sync first.</p>`;

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
      : `<p class="empty">No destinations yet. Sync first.</p>`;

    $("#overview-warnings").innerHTML = (data.warnings || []).length
      ? `<ul>${(data.warnings || [])
          .map((w) => `<li>${escapeHtml(w.message)}</li>`)
          .join("")}</ul>`
      : `<p class="empty">No warnings in cache.</p>`;

    $("#top-users").querySelectorAll("tr.clickable").forEach((tr) => {
      tr.addEventListener("click", () => openUser(tr.dataset.user));
    });

    try {
      const users = await api("/api/users");
      const rows = (users.users || [])
        .map((u) => {
          const nodes = (u.nodes || []).map((n) => n.name).join(", ") || "—";
          return `<tr class="clickable" data-user="${escapeHtml(u.tag || "")}">
            <td>${escapeHtml(u.tag || "?")}</td>
            <td><code>${escapeHtml((u.user_id || "").slice(0, 8))}…</code></td>
            <td>${escapeHtml(nodes)}</td>
          </tr>`;
        })
        .join("");
      $("#users-summary").innerHTML =
        `<p class="hint">Users (${escapeHtml(users.source || "cache")}): click for drill-down. ${escapeHtml(
          users.note || ""
        )}</p>` +
        (rows
          ? table(["Tag", "user_id", "Nodes"], rows)
          : `<p class="empty">No users in cache. Sync or Refresh users.</p>`);
      $("#users-summary").querySelectorAll("tr.clickable").forEach((tr) => {
        tr.addEventListener("click", () => openUser(tr.dataset.user));
      });
    } catch (err) {
      $("#users-summary").innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
    }
  }

  async function loadHealth() {
    const data = await api("/api/health");
    renderWarnings(data.warnings);
    const rows = (data.nodes || [])
      .map(
        (n) =>
          `<tr class="clickable" data-node="${escapeHtml(n.name)}">
            <td>${escapeHtml(n.name)}</td>
            <td>${statePill(n.ssh)}</td>
            <td>${statePill(n.proxy)}</td>
            <td>${statePill(n.accounting)}</td>
            <td>${escapeHtml(n.version || "—")}</td>
            <td>${statePill(n.clock || "-")}</td>
            <td>${escapeHtml(n.last_sync_at || "—")}</td>
          </tr>`
      )
      .join("");
    $("#health-table").innerHTML = rows
      ? table(
          ["NAME", "SSH", "PROXY", "ACCOUNTING", "VERSION", "CLOCK", "LAST_SYNC"],
          rows
        )
      : `<p class="empty">No nodes in fleet.json. Run <code>vcl-fleet init</code> / node add.</p>`;
    $("#health-table").querySelectorAll("tr.clickable").forEach((tr) => {
      tr.addEventListener("click", () => openNode(tr.dataset.node));
    });
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
      const p = data.probe || {};
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
instance_id: ${escapeHtml(p.instance_id || c.instance_id || "—")}
ssh/proxy/accounting: ${escapeHtml(p.ssh || "-")} / ${escapeHtml(p.proxy || "-")} / ${escapeHtml(
          p.accounting || "-"
        )}
version: ${escapeHtml(p.vincula_version || "—")}
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
            )}</td><td>${escapeHtml(n.status || "—")}</td><td><code>${escapeHtml(
              n.active_credential_id || "—"
            )}</code></td></tr>`
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
            ? table(["node", "enabled", "status", "credential_id"], nodes)
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

  async function refreshStatus(verify) {
    try {
      toast(verify ? "Running verify…" : "Refreshing status…");
      const data = await postJson(
        verify ? "/api/refresh/verify" : "/api/refresh/status",
        {}
      );
      toast(`${data.operation} exit ${data.exit_code}`);
      await Promise.all([loadOverview(), loadHealth()]);
    } catch (err) {
      toast(err.message);
    }
  }

  async function doSync() {
    if (
      !window.confirm(
        "Sync fleet audit cache now?\n\nThis updates local fleet.db via SSH.\nReseed remains CLI-only (vcl-fleet sync --reseed NAME)."
      )
    ) {
      return;
    }
    try {
      toast("Syncing…");
      const data = await postJson("/api/sync", {});
      toast(`sync exit ${data.exit_code}`);
      await Promise.all([loadOverview(), loadHealth()]);
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
        if (t.dataset.page === "health") loadHealth();
        if (t.dataset.page === "overview") loadOverview();
      })
    );
    $("#goto-health").addEventListener("click", () => {
      showPage("health");
      loadHealth();
    });
    $("#goto-audit").addEventListener("click", () => showPage("audit"));
    $("#audit-form").addEventListener("submit", runAudit);
    $("#btn-refresh-status").addEventListener("click", () => refreshStatus(false));
    $("#btn-verify").addEventListener("click", () => refreshStatus(true));
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
        await loadOverview();
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
  loadHealth().catch(() => {});
})();
