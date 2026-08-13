import { logger } from "./logger.js";
import {
  apiGet,
  diaryCard,
  escapeHtml,
  factsHtml,
  fillSourceControls,
  fmt,
  fmtPnl,
  fmtPx,
  pnlClass,
  scoreFacts,
  sourceParams,
  storeSource,
} from "./ledger.js";

logger.setPage("portfolio");

const els = {
  asOf: document.getElementById("as-of"),
  market: document.getElementById("market"),
  social: document.getElementById("social"),
  includeClosed: document.getElementById("include-closed"),
  reload: document.getElementById("reload"),
  status: document.getElementById("status-line"),
  body: document.getElementById("hold-body"),
  metaOpen: document.getElementById("meta-open"),
  metaCost: document.getElementById("meta-cost"),
  metaValue: document.getElementById("meta-value"),
  metaPnl: document.getElementById("meta-pnl"),
  dosTicker: document.getElementById("dos-ticker"),
  dosLead: document.getElementById("dos-lead"),
  dosBody: document.getElementById("dos-body"),
};

let positions = [];

function params() {
  const p = sourceParams({
    as_of: els.asOf.value,
    market: els.market.value,
    social: els.social.value,
  });
  if (els.includeClosed.value === "1") p.set("include_closed", "true");
  return p;
}

async function load() {
  els.status.textContent = "Loading holdings…";
  storeSource({ as_of: els.asOf.value, market: els.market.value, social: els.social.value });
  try {
    const data = await apiGet(`/api/portfolio?${params().toString()}`);
    positions = data.positions || [];
    const t = data.totals || {};
    els.metaOpen.textContent = String(t.open ?? 0);
    els.metaCost.textContent = fmtPx(t.cost_basis);
    els.metaValue.textContent = t.priced ? fmtPx(t.market_value) : "—";
    els.metaPnl.textContent = fmtPnl(t.pnl_abs, t.pnl_pct);
    els.metaPnl.className = pnlClass(t.pnl_abs);
    renderTable();
    els.status.textContent = positions.length
      ? `${positions.length} positions · ${data.meta?.market_mode} / ${data.meta?.social_mode}`
      : "No holdings yet — add from the desk drawer.";
    const hash = decodeURIComponent((location.hash || "").replace("#", "")).toUpperCase();
    if (hash) openDossier(hash);
    logger.info("portfolio load ok", { n: positions.length });
  } catch (err) {
    els.status.textContent = `Failed: ${err.message}`;
    els.status.className = "status-line error";
    logger.error("portfolio load failed", { message: err.message });
  }
}

function renderTable() {
  if (!positions.length) {
    els.body.innerHTML = `<tr class="state-row"><td colspan="6">No holdings. Open the desk drawer and use In holdings aufnehmen.</td></tr>`;
    return;
  }
  els.body.innerHTML = positions.map((pos) => {
    const pnl = pos.pnl || {};
    const thesis = (pos.thesis || "").slice(0, 64);
    return `<tr data-ticker="${escapeHtml(pos.ticker)}">
      <td class="ticker">${escapeHtml(pos.ticker)}${pos.status === "closed" ? " <span class='badge thin'>closed</span>" : ""}</td>
      <td class="num">${fmt(pnl.shares, 4)}</td>
      <td class="num">${fmtPx(pnl.avg_cost)}</td>
      <td class="num">${fmtPx(pnl.last_price)}</td>
      <td class="num ${pnlClass(pnl.pnl_abs)}">${escapeHtml(fmtPnl(pnl.pnl_abs, pnl.pnl_pct))}</td>
      <td>${escapeHtml(thesis)}${(pos.thesis || "").length > 64 ? "…" : ""}</td>
    </tr>`;
  }).join("");
}

async function openDossier(ticker) {
  const data = await apiGet(`/api/portfolio/${encodeURIComponent(ticker)}?${params().toString()}`);
  const pos = data.position;
  els.dosTicker.textContent = data.ticker;
  els.dosLead.textContent = data.held ? "Open holding" : (pos ? "Closed holding" : "No holding");
  if (!pos) {
    els.dosBody.innerHTML = `<p class="muted">No position for ${escapeHtml(ticker)}. Add it from the desk.</p>`;
    return;
  }
  const pnl = pos.pnl || {};
  els.dosBody.innerHTML = `
    <p class="pnl ${pnlClass(pnl.pnl_abs)}">${escapeHtml(fmtPnl(pnl.pnl_abs, pnl.pnl_pct))}</p>
    <dl class="facts">${factsHtml([
      ["Shares", fmt(pnl.shares, 4)],
      ["Avg cost / Kurs zu Kauf", fmtPx(pnl.avg_cost)],
      ["Last", fmtPx(pnl.last_price)],
      ["Cost basis", fmtPx(pnl.cost_basis)],
      ["Market value", fmtPx(pnl.market_value)],
      ["Opened", pos.opened_at || "—"],
    ])}</dl>
    <h3>Grund des Kaufens</h3>
    <p>${escapeHtml(data.buy_reason || pos.buy_reason || "—")}</p>
    <h3>These</h3>
    <p>${escapeHtml(data.thesis || pos.thesis || "—")}</p>
    <div class="compare-grid">
      <div>
        <h3>Daten zu Kauf</h3>
        <dl class="facts">${factsHtml(scoreFacts(data.purchase_snapshot))}</dl>
      </div>
      <div>
        <h3>Aktuelle Daten</h3>
        <dl class="facts">${factsHtml(scoreFacts(data.current_snapshot))}</dl>
      </div>
    </div>
    <h3>Tagebuch</h3>
    <div class="note-list">${(data.diary || []).map(diaryCard).join("") || "<p class='muted'>Keine Einträge.</p>"}</div>
    <p><a href="/?q=${encodeURIComponent(data.ticker)}">Open on desk</a> · <a href="/diary?ticker=${encodeURIComponent(data.ticker)}">Full diary</a></p>
  `;
}

fillSourceControls(els);
els.reload.addEventListener("click", load);
els.asOf.addEventListener("change", load);
els.market.addEventListener("change", load);
els.social.addEventListener("change", load);
els.includeClosed.addEventListener("change", load);
els.body.addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-ticker]");
  if (tr) {
    location.hash = tr.dataset.ticker;
    openDossier(tr.dataset.ticker).catch((err) => {
      els.status.textContent = err.message;
    });
  }
});
logger.info("portfolio boot");
load();
