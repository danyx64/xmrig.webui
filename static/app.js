const $ = (id) => document.getElementById(id);

const fmtRate = (value) => {
  value = Number(value || 0);
  const units = ["H/s", "kH/s", "MH/s", "GH/s"];
  let i = 0;
  while (value >= 1000 && i < units.length - 1) {
    value /= 1000;
    i++;
  }
  return `${value.toLocaleString(undefined, {
    maximumFractionDigits: value >= 100 ? 0 : value >= 10 ? 1 : 2
  })} ${units[i]}`;
};

const fmtXmr = (v) =>
  `${Number(v || 0).toLocaleString(undefined, {
    minimumFractionDigits: 6,
    maximumFractionDigits: 12
  })} XMR`;

const esc = (s) =>
  String(s ?? "").replace(/[&<>'"]/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;"
  }[c]));

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

function toast(message, error = false) {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast show${error ? " error" : ""}`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => (el.className = "toast"), 2800);
}

function renderMiners(items) {
  const body = $("minersBody");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="9" class="empty">Nessun server configurato</td></tr>';
    return;
  }
  body.innerHTML = items.map((m) => `
    <tr>
      <td>
        <div class="server-name">${esc(m.name)}</div>
        <div class="server-sub">${esc(m.api_url)}</div>
      </td>
      <td><span class="status ${m.online ? "ok" : "bad"}">${m.online ? "online" : "offline"}</span></td>
      <td>${m.online ? fmtRate(m.hashrate_10s) : "—"}</td>
      <td>${m.online ? fmtRate(m.hashrate_60s) : "—"}</td>
      <td>${m.online ? fmtRate(m.hashrate_15m) : "—"}</td>
      <td>${m.temperature_c != null ? `${Number(m.temperature_c).toFixed(1)} °C` : "—"}</td>
      <td>${m.online ? `${Number(m.accepted || 0).toLocaleString()} / ${Number(m.rejected || 0).toLocaleString()}` : "—"}</td>
      <td>${esc(m.pool || "—")}</td>
      <td><button class="link-danger" onclick="removeMiner(${m.id})">Rimuovi</button></td>
    </tr>
  `).join("");
}

function renderPoolWorkers(items) {
  const body = $("poolWorkersBody");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty">Nessun worker disponibile</td></tr>';
    return;
  }
  body.innerHTML = items.map((w) => `
    <tr>
      <td>${esc(w.name)}</td>
      <td>${fmtRate(w.hashrate)}</td>
      <td>${esc(w.algo || "—")}</td>
      <td>${Number(w.valid || 0).toLocaleString()}</td>
      <td>${Number(w.invalid || 0).toLocaleString()}</td>
    </tr>
  `).join("");
}

function renderOverview(data) {
  const pool = data.pool || {};
  const totals = data.totals || {};

  $("localHashrate").textContent = fmtRate(totals.hashrate);
  $("poolHashrate").textContent = pool.online ? fmtRate(pool.hashrate) : "—";
  $("pendingXmr").textContent = pool.configured ? fmtXmr(pool.pending_xmr) : "—";
  $("paidXmr").textContent = pool.configured ? fmtXmr(pool.paid_xmr) : "—";
  $("onlineMiners").textContent = `${totals.online || 0}/${totals.configured || 0}`;
  $("maxTemp").textContent = totals.max_temp_c != null ? `${Number(totals.max_temp_c).toFixed(1)} °C` : "—";

  $("detailPool").textContent = pool.pool_url || "—";
  $("detailApi").textContent = pool.api_base || "—";
  $("detailWallet").textContent = pool.wallet || "—";
  $("detailValid").textContent = Number(pool.valid_shares || 0).toLocaleString();
  $("detailInvalid").textContent = Number(pool.invalid_shares || 0).toLocaleString();
  $("detailHashes").textContent = Number(pool.total_hashes || 0).toLocaleString();

  $("poolStatus").textContent = pool.online ? "online" : (pool.configured ? "errore" : "non configurata");
  $("poolStatus").className = `status ${pool.online ? "ok" : pool.configured ? "bad" : "neutral"}`;

  renderMiners(data.miners || []);
  renderPoolWorkers(pool.workers || []);
}

async function loadAll() {
  try {
    $("refreshState").textContent = "Aggiornamento…";
    const data = await api("/api/overview");
    renderOverview(data);
    $("refreshState").textContent =
      `Aggiornato ${new Date(data.refreshed_at * 1000).toLocaleTimeString()}`;
  } catch (e) {
    $("refreshState").textContent = "Errore aggiornamento";
    toast(e.message, true);
  }
}

async function openSettings() {
  try {
    const s = await api("/api/settings");
    $("poolUrl").value = s.pool_url || "";
    $("wallet").value = s.wallet || "";
    $("settingsDialog").showModal();
  } catch (e) {
    toast(e.message, true);
  }
}

async function saveSettings() {
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        pool_url: $("poolUrl").value,
        wallet: $("wallet").value
      })
    });
    $("settingsDialog").close();
    toast("Impostazioni salvate");
    loadAll();
  } catch (e) {
    toast(e.message, true);
  }
}

function openMiner() {
  $("minerName").value = "";
  $("minerApi").value = "";
  $("minerAgent").value = "";
  $("minerToken").value = "";
  $("minerDialog").showModal();
}

async function saveMiner() {
  try {
    await api("/api/miners", {
      method: "POST",
      body: JSON.stringify({
        name: $("minerName").value,
        api_url: $("minerApi").value,
        agent_url: $("minerAgent").value,
        token: $("minerToken").value
      })
    });
    $("minerDialog").close();
    toast("Server aggiunto");
    loadAll();
  } catch (e) {
    toast(e.message, true);
  }
}

async function removeMiner(id) {
  if (!confirm("Rimuovere questo server?")) return;
  try {
    await api(`/api/miners/${id}`, { method: "DELETE" });
    toast("Server rimosso");
    loadAll();
  } catch (e) {
    toast(e.message, true);
  }
}

window.removeMiner = removeMiner;

$("refreshBtn").addEventListener("click", loadAll);
$("settingsBtn").addEventListener("click", openSettings);
$("saveSettings").addEventListener("click", saveSettings);
$("addMinerBtn").addEventListener("click", openMiner);
$("saveMiner").addEventListener("click", saveMiner);

loadAll();
setInterval(loadAll, 30000);
