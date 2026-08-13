import { logger } from "./logger.js";
import {
  apiGet,
  apiSend,
  diaryCard,
  escapeHtml,
  factsHtml,
  fmt,
  fmtPnl,
  fmtPx,
  pnlClass,
  scoreFacts,
  storeSource,
  todayISO,
} from "./ledger.js";

logger.setPage("desk");

const state = {
  view: "standing",
  data: null,
  loading: false,
  sectorsPopulated: false,
  held: new Set(),
  dossier: null,
};

const els = {
  asOf: document.getElementById("as-of"),
  market: document.getElementById("market"),
  social: document.getElementById("social"),
  filter: document.getElementById("filter"),
  sort: document.getElementById("sort"),
  preset: document.getElementById("preset"),
  sector: document.getElementById("sector"),
  reload: document.getElementById("reload"),
  exportCsv: document.getElementById("export-csv"),
  statusLine: document.getElementById("status-line"),
  standingBody: document.getElementById("standing-body"),
  heatBody: document.getElementById("heat-body"),
  boardStanding: document.getElementById("board-standing"),
  boardHeat: document.getElementById("board-heat"),
  drawer: document.getElementById("drawer"),
  scrim: document.getElementById("scrim"),
  drawerClose: document.getElementById("drawer-close"),
  drawerTicker: document.getElementById("drawer-ticker"),
  drawerSector: document.getElementById("drawer-sector"),
  drawerLead: document.getElementById("drawer-lead"),
  drawerFlags: document.getElementById("drawer-flags"),
  drawerBars: document.getElementById("drawer-bars"),
  drawerFacts: document.getElementById("drawer-facts"),
  drawerNote: document.getElementById("drawer-note"),
  holdingEmpty: document.getElementById("holding-empty"),
  holdingBody: document.getElementById("holding-body"),
  holdingForm: document.getElementById("holding-form"),
  holdShares: document.getElementById("hold-shares"),
  holdCost: document.getElementById("hold-cost"),
  holdReason: document.getElementById("hold-reason"),
  holdThesis: document.getElementById("hold-thesis"),
  diaryForm: document.getElementById("diary-form"),
  diaryComment: document.getElementById("diary-comment"),
  drawerDiary: document.getElementById("drawer-diary"),
  metaAsof: document.getElementById("meta-asof"),
  metaUniverse: document.getElementById("meta-universe"),
  metaN: document.getElementById("meta-n"),
  metaPlaceholder: document.getElementById("meta-placeholder"),
  footMethod: document.getElementById("foot-method"),
  footPosture: document.getElementById("foot-posture"),
  footServe: document.getElementById("foot-serve"),
  footStaleness: document.getElementById("foot-staleness"),
  fixtureBanner: document.getElementById("fixture-banner"),
};

function tiltClass(v) {
  return Number(v) >= 0 ? "tilt-pos" : "tilt-neg";
}

function queryParams() {
  const params = new URLSearchParams({
    as_of: els.asOf.value || todayISO(),
    sort: els.sort.value,
    preset: els.preset.value,
    market: els.market.value,
    social: els.social.value,
    history_days: "14",
  });
  if (els.filter.value.trim()) params.set("q", els.filter.value.trim());
  if (els.sector.value) params.set("sector", els.sector.value);
  return params;
}

function setStatus(message, kind = "") {
  els.statusLine.textContent = message || "";
  els.statusLine.className = `status-line ${kind}`.trim();
}

function setLoading(isLoading) {
  state.loading = isLoading;
  document.body.classList.toggle("is-loading", isLoading);
  if (isLoading) {
    setStatus("Loading snapshot…", "loading");
    els.standingBody.innerHTML = `<tr class="state-row"><td colspan="9">Loading snapshot…</td></tr>`;
    els.heatBody.innerHTML = `<tr class="state-row"><td colspan="9">Loading snapshot…</td></tr>`;
  }
}

async function loadSnapshot() {
  setLoading(true);
  const params = queryParams();
  logger.info("snapshot load start", {
    as_of: params.get("as_of"),
    preset: params.get("preset"),
    sort: params.get("sort"),
    sector: params.get("sector") || null,
    q: params.get("q") || null,
  });
  try {
    const res = await fetch(`/api/snapshot?${params.toString()}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    state.data = await res.json();
    storeSource({
      as_of: els.asOf.value,
      market: els.market.value,
      social: els.social.value,
    });
    await loadHeld();
    renderMeta();
    populateSectors();
    renderTables();
    const n = state.data.standings.length;
    const m = state.data.meta || {};
    const mode = `${m.market_mode || els.market.value} / ${m.social_mode || els.social.value}`;
    const serve = m.served_from ? ` · served ${m.served_from}` : "";
    logger.info("snapshot load ok", {
      n,
      universe: m.universe_id,
      as_of: m.as_of,
      served_from: m.served_from,
    });
    setStatus(
      n === 0
        ? "No rows match this preset / filter."
        : `${n} names · ${mode}${serve} · preset ${els.preset.value}`,
      n === 0 ? "empty" : "",
    );
  } catch (err) {
    showError(err);
  } finally {
    state.loading = false;
    document.body.classList.remove("is-loading");
  }
}

function renderMeta() {
  const m = state.data.meta;
  els.metaAsof.textContent = m.as_of;
  els.metaUniverse.textContent = m.universe_as_of
    ? `${m.universe_id} @ ${m.universe_as_of}`
    : m.universe_id;
  els.metaN.textContent = String(m.n_names);
  els.metaPlaceholder.textContent = m.placeholder ? "placeholder" : "frozen";
  els.footMethod.textContent = `${m.score_kind} · ${m.methodology_version}`;
  const tiltNote = m.tilt_max != null ? ` · tilt≤${m.tilt_max}` : "";
  const attn = m.attention_mode ? ` · ${m.attention_mode}` : "";
  els.footPosture.textContent =
    `${m.market_mode || m.market_provider} · ${m.social_mode || m.social_provider}${tiltNote}${attn}`;
  els.footServe.textContent = m.served_from
    ? `served ${m.served_from}${m.created_at_utc ? ` · ingested ${m.created_at_utc}` : ""}`
    : "served —";
  const stale = m.provider_staleness_utc || {};
  const parts = [];
  if (stale.market) parts.push(`market ${stale.market}`);
  if (stale.social) parts.push(`attention ${stale.social}`);
  if (stale.scored) parts.push(`scored ${stale.scored}`);
  els.footStaleness.textContent = parts.length ? parts.join(" · ") : "staleness —";

  const socialFixture = m.social_is_fixture === true || (m.social_mode || els.social.value) === "fixture";
  els.fixtureBanner.classList.toggle("hidden", !socialFixture);
}

function populateSectors() {
  if (state.sectorsPopulated) return;
  const counts = state.data.meta.sector_counts || {};
  const sectors = Object.keys(counts).sort();
  for (const sector of sectors) {
    const opt = document.createElement("option");
    opt.value = sector;
    opt.textContent = `${sector} (${counts[sector]})`;
    els.sector.appendChild(opt);
  }
  state.sectorsPopulated = true;
}

function standingRow(row) {
  const held = state.held.has(row.ticker);
  return `<tr data-ticker="${row.ticker}" class="${held ? "is-held" : ""}">
    <td class="ticker">${row.ticker}${held ? ' <span class="held-dot" title="In holdings">●</span>' : ""}</td>
    <td>${row.sector}</td>
    <td class="num">${fmt(row.value)}</td>
    <td class="num">${fmt(row.quality)}</td>
    <td class="num">${fmt(row.momentum)}</td>
    <td class="num">${fmt(row.composite_standing)}</td>
    <td class="num ${tiltClass(row.attention_tilt)}">${fmt(row.attention_tilt, 2)}</td>
    <td class="num"><strong>${fmt(row.final_standing)}</strong></td>
    <td><span class="badge ${row.social_badge}">${row.social_badge}</span></td>
  </tr>`;
}

function heatRow(row) {
  const width = Math.max(4, Math.min(100, Number(row.s_used) || 0));
  const held = state.held.has(row.ticker);
  return `<tr data-ticker="${row.ticker}" class="${held ? "is-held" : ""}">
    <td class="ticker">${row.ticker}${held ? ' <span class="held-dot" title="In holdings">●</span>' : ""}</td>
    <td class="num">
      <div class="heat-cell">
        <div class="heat-track"><div class="heat-fill" style="width:${width}%"></div></div>
        <span>${fmt(row.s_used)}</span>
      </div>
    </td>
    <td class="num">${fmt(row.s_obs)}</td>
    <td class="num">${fmt(row.s_used)}</td>
    <td class="num">${fmt(row.n, 0)}</td>
    <td class="num">${fmt(row.confidence_c, 2)}</td>
    <td class="num">${fmt(row.neg_share, 2)}</td>
    <td class="num ${tiltClass(row.attention_tilt)}">${fmt(row.attention_tilt, 2)}</td>
    <td class="num">${fmt(row.final_standing)}</td>
  </tr>`;
}

function renderTables() {
  const { standings, heat } = state.data;
  if (!standings.length) {
    const empty = `<tr class="state-row"><td colspan="9">No rows match this preset / filter.</td></tr>`;
    els.standingBody.innerHTML = empty;
    els.heatBody.innerHTML = empty;
    return;
  }
  els.standingBody.innerHTML = standings.map(standingRow).join("");
  els.heatBody.innerHTML = heat.map(heatRow).join("");
  requestAnimationFrame(() => {
    document.querySelectorAll(".heat-fill").forEach((el) => {
      const w = el.style.width;
      el.style.width = "0%";
      requestAnimationFrame(() => {
        el.style.width = w;
      });
    });
  });
}

function setView(view) {
  state.view = view;
  logger.info("view change", { view });
  document.querySelectorAll(".tab").forEach((btn) => {
    const active = btn.dataset.view === view;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  els.boardStanding.classList.toggle("hidden", view !== "standing");
  els.boardHeat.classList.toggle("hidden", view !== "heat");
}

function openDrawer(ticker) {
  const row = state.data.standings.find((r) => r.ticker === ticker)
    || state.data.heat.find((r) => r.ticker === ticker);
  if (!row) return;
  logger.info("drawer open", { ticker: row.ticker, sector: row.sector });

  const m = state.data.meta;
  els.drawerTicker.textContent = row.ticker;
  els.drawerSector.textContent = row.sector;
  els.drawerLead.textContent = "Evidence breakdown — descriptive modules only";

  const flags = [];
  if (row.sector_low_confidence) {
    flags.push(`<span class="flag warn">sector low confidence (&lt;30 peers)</span>`);
  }
  flags.push(`<span class="flag">${row.social_badge} social</span>`);
  flags.push(`<span class="flag">c=${fmt(row.confidence_c, 2)} · n=${fmt(row.n, 0)}</span>`);
  if (row.value_coverage != null) {
    flags.push(`<span class="flag">value coverage ${fmt(row.value_coverage, 2)}</span>`);
  }
  if (row.value_ev_rung) {
    flags.push(`<span class="flag">EV ${row.value_ev_rung}</span>`);
  }
  if (m.social_is_fixture || m.social_mode === "fixture") {
    flags.push(`<span class="flag warn">fixture attention</span>`);
  }
  els.drawerFlags.innerHTML = flags.join(" ");

  els.drawerBars.innerHTML = [
    bar("Value", row.value, "v"),
    bar("Quality", row.quality, "q"),
    bar("Momentum (sector)", row.momentum, "m"),
    bar("Momentum (global display)", row.momentum_global, "m"),
    bar("Composite Standing", row.composite_standing, "v"),
    bar("Attention Tilt (+50 baseline)", 50 + Number(row.attention_tilt) * 5, "tilt", true),
  ].join("");

  els.drawerFacts.innerHTML = [
    fact("Final Standing", fmt(row.final_standing)),
    fact("Attention Tilt", fmt(row.attention_tilt, 2)),
    fact("S_obs / S_used", `${fmt(row.s_obs)} / ${fmt(row.s_used)}`),
    fact("Mentions n", fmt(row.n, 0)),
    fact("Confidence c", fmt(row.confidence_c, 2)),
    fact("Neg share", fmt(row.neg_share, 2)),
    fact("Momentum (global)", fmt(row.momentum_global)),
    fact("Social badge", row.social_badge),
    fact("Sector low-confidence", row.sector_low_confidence ? "yes" : "no"),
    fact("Source posture", `${m.market_provider} / ${m.social_provider}`),
    fact("Last price", fmtPx(row.last_price)),
  ].join("");

  els.drawerNote.innerHTML =
    "Composite Standing averages sector-relative V/Q/M. "
    + "Attention Tilt uses tanh + shrinkage around neutral 50 and cannot dominate the base. "
    + `<strong>${m.market_mode || "market"} · ${m.social_mode || "social"}</strong>. `
    + "Tagebuch und Holdings sind persönliche Notizen, keine Anlageberatung.";

  renderHolding(null);
  els.drawerDiary.innerHTML = "";
  loadDossier(row.ticker);

  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
  els.scrim.hidden = false;
  requestAnimationFrame(() => {
    els.drawerBars.querySelectorAll(".bar-fill").forEach((el) => {
      el.style.width = el.dataset.width;
    });
  });
}

function bar(label, value, cls, _raw = false) {
  const width = Math.max(0, Math.min(100, Number(value) || 0));
  return `<div class="bar-row">
    <span><span>${label}</span><span>${fmt(value)}</span></span>
    <div class="bar-track"><div class="bar-fill ${cls}" data-width="${width}%"></div></div>
  </div>`;
}

function fact(label, value) {
  return `<div><dt>${label}</dt><dd>${value}</dd></div>`;
}

function closeDrawer() {
  els.drawer.classList.remove("open");
  els.drawer.setAttribute("aria-hidden", "true");
  els.scrim.hidden = true;
}

function exportCsv() {
  const params = queryParams();
  logger.info("csv export", {
    as_of: params.get("as_of"),
    preset: params.get("preset"),
    sector: params.get("sector") || null,
    q: params.get("q") || null,
  });
  window.location.href = `/api/snapshot.csv?${params.toString()}`;
}

function sourceBody() {
  return {
    as_of: els.asOf.value || todayISO(),
    market: els.market.value,
    social: els.social.value,
  };
}

async function loadHeld() {
  try {
    const data = await apiGet(`/api/portfolio?${queryParams().toString()}`);
    state.held = new Set(data.held_tickers || []);
  } catch (err) {
    logger.warn("portfolio held load failed", { message: String(err) });
    state.held = new Set();
  }
}

async function loadDossier(ticker) {
  try {
    const data = await apiGet(`/api/portfolio/${encodeURIComponent(ticker)}?${queryParams().toString()}`);
    state.dossier = data;
    renderHolding(data);
    els.drawerDiary.innerHTML = (data.diary || []).slice(0, 6).map(diaryCard).join("")
      || `<p class="muted">Noch keine Tagebuch-Einträge.</p>`;
  } catch (err) {
    logger.warn("dossier load failed", { ticker, message: String(err) });
  }
}

function renderHolding(data) {
  const pos = data && data.position;
  const held = Boolean(data && data.held && pos);
  els.holdingEmpty.classList.toggle("hidden", held);
  els.holdingBody.classList.toggle("hidden", !held);
  els.holdingForm.classList.toggle("hidden", held);
  if (!held) {
    const row = state.data && (
      state.data.standings.find((r) => r.ticker === els.drawerTicker.textContent)
      || {}
    );
    if (row.last_price != null) els.holdCost.value = Number(row.last_price).toFixed(2);
    return;
  }
  const pnl = pos.pnl || {};
  const buy = data.purchase_snapshot || pos.purchase_snapshot;
  const cur = data.current_snapshot;
  els.holdingBody.innerHTML = `
    <p class="pnl ${pnlClass(pnl.pnl_abs)}">${escapeHtml(fmtPnl(pnl.pnl_abs, pnl.pnl_pct))}</p>
    <dl class="facts">
      ${factsHtml([
        ["Shares", fmt(pnl.shares, 4)],
        ["Avg cost", fmtPx(pnl.avg_cost)],
        ["Last", fmtPx(pnl.last_price)],
        ["Opened", pos.opened_at || "—"],
      ])}
    </dl>
    <h4>Grund des Kaufens</h4>
    <p>${escapeHtml(pos.buy_reason || data.buy_reason || "—")}</p>
    <h4>These</h4>
    <p>${escapeHtml(pos.thesis || data.thesis || "—")}</p>
    <div class="compare-grid">
      <div>
        <h4>Daten zu Kauf</h4>
        <dl class="facts">${factsHtml(scoreFacts(buy))}</dl>
      </div>
      <div>
        <h4>Aktuelle Daten</h4>
        <dl class="facts">${factsHtml(scoreFacts(cur))}</dl>
      </div>
    </div>
    <p><a href="/portfolio#${encodeURIComponent(pos.ticker)}">Open in Portfolio</a>
       · <a href="/diary?ticker=${encodeURIComponent(pos.ticker)}">Diary</a></p>
  `;
}

function bind() {
  els.asOf.value = todayISO();
  els.reload.addEventListener("click", () => loadSnapshot());
  els.exportCsv.addEventListener("click", exportCsv);
  els.asOf.addEventListener("change", () => loadSnapshot());
  els.market.addEventListener("change", () => loadSnapshot());
  els.social.addEventListener("change", () => loadSnapshot());
  els.sort.addEventListener("change", () => loadSnapshot());
  els.preset.addEventListener("change", () => loadSnapshot());
  els.sector.addEventListener("change", () => loadSnapshot());
  let timer;
  els.filter.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => loadSnapshot(), 180);
  });
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
  els.standingBody.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-ticker]");
    if (tr) openDrawer(tr.dataset.ticker);
  });
  els.heatBody.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-ticker]");
    if (tr) openDrawer(tr.dataset.ticker);
  });
  els.drawerClose.addEventListener("click", closeDrawer);
  els.scrim.addEventListener("click", closeDrawer);
  els.holdingForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const ticker = els.drawerTicker.textContent;
    try {
      await apiSend("/api/portfolio", "POST", {
        ticker,
        shares: Number(els.holdShares.value),
        avg_cost: Number(els.holdCost.value),
        buy_reason: els.holdReason.value,
        thesis: els.holdThesis.value,
        ...sourceBody(),
      });
      logger.info("holding saved", { ticker });
      els.holdReason.value = "";
      els.holdThesis.value = "";
      await loadHeld();
      renderTables();
      await loadDossier(ticker);
    } catch (err) {
      setStatus(`Holding not saved: ${err.message}`, "error");
    }
  });
  els.diaryForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const ticker = els.drawerTicker.textContent;
    try {
      await apiSend("/api/diary", "POST", {
        ticker,
        comment: els.diaryComment.value,
        kind: "observation",
        ...sourceBody(),
      });
      els.diaryComment.value = "";
      logger.info("diary appended", { ticker });
      await loadDossier(ticker);
    } catch (err) {
      setStatus(`Diary not saved: ${err.message}`, "error");
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDrawer();
    if (e.key === "/" && document.activeElement !== els.filter) {
      e.preventDefault();
      els.filter.focus();
    }
  });
}

function showError(err) {
  const msg = err && err.message ? err.message : String(err);
  logger.error("snapshot load failed", { message: msg });
  setStatus(`Failed to load: ${msg}`, "error");
  const row = `<tr class="state-row error"><td colspan="9">Failed to load: ${msg}</td></tr>`;
  els.standingBody.innerHTML = row;
  els.heatBody.innerHTML = row;
}

logger.info("desk boot");
bind();
loadSnapshot();
