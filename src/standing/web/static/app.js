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
  activeTicker: null,
  modalKind: null,
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
  bookBody: document.getElementById("book-body"),
  reviewBody: document.getElementById("review-body"),
  journalFeed: document.getElementById("journal-feed"),
  boardStanding: document.getElementById("board-standing"),
  boardHeat: document.getElementById("board-heat"),
  boardBook: document.getElementById("board-book"),
  boardReview: document.getElementById("board-review"),
  boardRecal: document.getElementById("board-recal"),
  drawer: document.getElementById("drawer"),
  scrim: document.getElementById("scrim"),
  drawerClose: document.getElementById("drawer-close"),
  drawerTicker: document.getElementById("drawer-ticker"),
  drawerSector: document.getElementById("drawer-sector"),
  drawerLead: document.getElementById("drawer-lead"),
  drawerFlags: document.getElementById("drawer-flags"),
  drawerActions: document.getElementById("drawer-actions"),
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
  diaryKind: document.getElementById("diary-kind"),
  diaryComment: document.getElementById("diary-comment"),
  drawerDiary: document.getElementById("drawer-diary"),
  drawerPortfolio: document.getElementById("drawer-portfolio"),
  drawerScorePair: document.getElementById("drawer-score-pair"),
  drawerScoreChart: document.getElementById("drawer-score-chart"),
  drawerPortfolioFacts: document.getElementById("drawer-portfolio-facts"),
  drawerJournal: document.getElementById("drawer-journal"),
  metaAsof: document.getElementById("meta-asof"),
  metaUniverse: document.getElementById("meta-universe"),
  metaN: document.getElementById("meta-n"),
  metaPlaceholder: document.getElementById("meta-placeholder"),
  footMethod: document.getElementById("foot-method"),
  footPosture: document.getElementById("foot-posture"),
  footServe: document.getElementById("foot-serve"),
  footStaleness: document.getElementById("foot-staleness"),
  fixtureBanner: document.getElementById("fixture-banner"),
  modal: document.getElementById("modal"),
  modalScrim: document.getElementById("modal-scrim"),
  modalClose: document.getElementById("modal-close"),
  modalTitle: document.getElementById("modal-title"),
  modalLead: document.getElementById("modal-lead"),
  modalForm: document.getElementById("modal-form"),
  modalError: document.getElementById("modal-error"),
  recalForm: document.getElementById("recal-form"),
  recalWindow: document.getElementById("recal-window"),
  recalMinHold: document.getElementById("recal-min-hold"),
  recalAsOf: document.getElementById("recal-as-of"),
  recalSummary: document.getElementById("recal-summary"),
  recalSuggestions: document.getElementById("recal-suggestions"),
  recalMarkdown: document.getElementById("recal-markdown"),
  reportList: document.getElementById("report-list"),
  btnBuy: document.getElementById("btn-buy"),
  btnWatchlist: document.getElementById("btn-watchlist"),
  btnJournal: document.getElementById("btn-journal"),
  btnRefreshBook: document.getElementById("btn-refresh-book"),
  btnRefreshReview: document.getElementById("btn-refresh-review"),
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
    els.standingBody.innerHTML = `<tr class="state-row"><td colspan="10">Loading snapshot…</td></tr>`;
    els.heatBody.innerHTML = `<tr class="state-row"><td colspan="9">Loading snapshot…</td></tr>`;
  }
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body.detail;
    const msg = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
        : res.statusText;
    throw new Error(msg || "Request failed");
  }
  return body;
}

function snapshotSeedFromRow(row) {
  if (!row) return null;
  const m = state.data?.meta || {};
  return {
    as_of: m.as_of || els.asOf.value || todayISO(),
    universe_version: m.universe_id || "desk",
    score: Number(row.final_standing),
    pillar_fundamentals: row.value == null ? null : Number(row.value),
    pillar_momentum: row.momentum == null ? null : Number(row.momentum),
    pillar_attention: row.s_used == null ? null : Number(row.s_used),
    coverage_flags: {
      value_coverage: row.value_coverage,
      value_ev_rung: row.value_ev_rung,
      sector_low_confidence: row.sector_low_confidence,
    },
    provider_state: {
      market_mode: m.market_mode,
      social_mode: m.social_mode,
      market_provider: m.market_provider,
      social_provider: m.social_provider,
    },
  };
}

function findRow(ticker) {
  if (!state.data) return null;
  return state.data.standings.find((r) => r.ticker === ticker)
    || state.data.heat.find((r) => r.ticker === ticker)
    || null;
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
    if (state.view === "book") await loadBook();
    if (state.view === "review") await loadReview();
    if (state.view === "recal") await loadReportList();
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
  if (m.portfolio_db_ok === false) {
    parts.push(`portfolio DB error`);
  } else if (m.portfolio_db) {
    parts.push(`portfolio ok`);
  }
  if (m.as_of_fallback) {
    parts.push(`as_of fallback from ${m.requested_as_of || "today"}`);
  }
  els.footStaleness.textContent = parts.length ? parts.join(" · ") : "staleness —";

  const socialFixture = m.social_is_fixture === true || (m.social_mode || els.social.value) === "fixture";
  els.fixtureBanner.classList.toggle("hidden", !socialFixture);

  if (m.portfolio_db_ok === false && m.portfolio_db_error) {
    setStatus(`Portfolio DB issue: ${m.portfolio_db_error}`, "error");
  }
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
  const held = row.portfolio && row.portfolio.held;
  const holdCell = held ? portfolioHoldCell(row.portfolio) : `<td class="dim">—</td>`;
  const heldClass = held ? " held" : "";
  return `<tr data-ticker="${row.ticker}" class="${heldClass.trim()}">
    <td class="ticker">${row.ticker}${held ? ' <span class="held-badge">held</span>' : ""}</td>
    <td>${row.sector}</td>
    <td class="num">${fmt(row.value)}</td>
    <td class="num">${fmt(row.quality)}</td>
    <td class="num">${fmt(row.momentum)}</td>
    <td class="num">${fmt(row.composite_standing)}</td>
    <td class="num ${tiltClass(row.attention_tilt)}">${fmt(row.attention_tilt, 2)}</td>
    <td class="num"><strong>${fmt(row.final_standing)}</strong></td>
    <td><span class="badge ${row.social_badge}">${row.social_badge}</span></td>
    ${holdCell}
  </tr>`;
}

function portfolioHoldCell(p) {
  const drift = p.score_drift;
  const bucket = p.drift_bucket || "n/a";
  const bucketClass = bucket === "n/a" ? "na" : bucket;
  const driftTxt = drift == null ? "—" : `${drift >= 0 ? "+" : ""}${Number(drift).toFixed(1)}`;
  return `<td class="hold-cell">
    <span class="score-pair-inline">
      <span title="score @ entry">${fmt(p.score_at_entry)}</span>
      <span class="arrow">→</span>
      <span title="score now">${fmt(p.score_now)}</span>
      <span class="drift drift-${bucketClass}">${driftTxt}</span>
    </span>
  </td>`;
}

function heatRow(row) {
  const width = Math.max(4, Math.min(100, Number(row.s_used) || 0));
  const held = row.portfolio && row.portfolio.held;
  const heldClass = held ? " held" : "";
  return `<tr data-ticker="${row.ticker}" class="${heldClass.trim()}">
    <td class="ticker">${row.ticker}${held ? ' <span class="held-badge">held</span>' : ""}</td>
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
    const empty = `<tr class="state-row"><td colspan="10">No rows match this preset / filter.</td></tr>`;
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
  const boards = {
    standing: els.boardStanding,
    heat: els.boardHeat,
    book: els.boardBook,
    review: els.boardReview,
    recal: els.boardRecal,
  };
  Object.entries(boards).forEach(([key, el]) => {
    el.classList.toggle("hidden", key !== view);
  });
  if (view === "book") loadBook();
  if (view === "review") loadReview();
  if (view === "recal") loadReportList();
}

async function loadBook() {
  try {
    const [book, journal] = await Promise.all([
      api("/api/portfolio"),
      api("/api/portfolio/journal?limit=40"),
    ]);
    if (!book.positions.length) {
      els.bookBody.innerHTML = `<tr class="state-row"><td colspan="10">No open positions yet. Use <a href="/trade">Trade → Kauf</a> or open a ticker on Standing.</td></tr>`;
    } else {
      els.bookBody.innerHTML = book.positions.map((p) => {
        const bucket = p.drift_bucket || "n/a";
        const bucketClass = bucket === "n/a" ? "na" : bucket;
        const drift = p.score_drift;
        const driftTxt = drift == null ? "—" : `${drift >= 0 ? "+" : ""}${Number(drift).toFixed(1)}`;
        return `<tr data-ticker="${p.ticker}" class="held">
          <td class="ticker">${p.ticker} <span class="held-badge">held</span></td>
          <td class="num">${fmt(p.entry_price, 2)}</td>
          <td class="num">${p.now_px != null ? fmt(p.now_px, 2) : "—"}</td>
          <td class="num">${p.pnl_pct != null ? `${fmt(p.pnl_pct, 2)}%` : "—"}</td>
          <td class="num">${fmt(p.score_at_entry)}</td>
          <td class="num">${fmt(p.score_now)}</td>
          <td class="num drift drift-${bucketClass}">${driftTxt}</td>
          <td class="num">${p.dist_to_target_pct != null ? `${fmt(p.dist_to_target_pct, 1)}%` : "—"}</td>
          <td class="num">${p.dist_to_stop_pct != null ? `${fmt(p.dist_to_stop_pct, 1)}%` : "—"}</td>
          <td><a class="ghost tiny" href="/trade?side=sell&ticker=${encodeURIComponent(p.ticker)}">Verkauf</a></td>
        </tr>`;
      }).join("");
    }
    els.journalFeed.innerHTML = journal.entries.length
      ? journal.entries.map((e) => `
        <li>
          <div class="jf-head">
            <strong>${escapeHtml(e.ticker)}</strong>
            <span class="jtype">${escapeHtml(e.entry_type)}</span>
            <time datetime="${e.ts}">${formatLocal(e.ts)}</time>
          </div>
          <p>${escapeHtml(e.body)}</p>
        </li>`).join("")
      : `<li class="dim">No journal entries yet.</li>`;
  } catch (err) {
    els.bookBody.innerHTML = `<tr class="state-row error"><td colspan="10">${escapeHtml(err.message)}</td></tr>`;
    els.journalFeed.innerHTML = `<li class="dim">${escapeHtml(err.message)}</li>`;
  }
}

async function loadReview() {
  try {
    const data = await api("/api/portfolio/review");
    if (!data.rows.length) {
      els.reviewBody.innerHTML = `<tr class="state-row"><td colspan="7">No closed positions yet.</td></tr>`;
      return;
    }
    els.reviewBody.innerHTML = data.rows.map((r) => `
      <tr>
        <td class="ticker">${r.ticker}</td>
        <td class="num">${r.hold_days}</td>
        <td class="num">${fmt(r.realized_return, 4)}</td>
        <td class="num">${r.benchmark_return == null ? "—" : fmt(r.benchmark_return, 4)}</td>
        <td class="num">${r.decile_return == null ? "—" : fmt(r.decile_return, 4)}</td>
        <td class="num">${r.excess_vs_benchmark == null ? "—" : fmt(r.excess_vs_benchmark, 4)}</td>
        <td><span class="outcome ${r.thesis_outcome}">${r.thesis_outcome}</span></td>
      </tr>`).join("");
  } catch (err) {
    els.reviewBody.innerHTML = `<tr class="state-row error"><td colspan="7">${escapeHtml(err.message)}</td></tr>`;
  }
}

async function loadReportList() {
  try {
    const data = await api("/api/portfolio/reports");
    if (!data.reports.length) {
      els.reportList.innerHTML = `<li class="dim">No reports yet. Run recalibrate.</li>`;
      return;
    }
    els.reportList.innerHTML = data.reports.map((r) =>
      `<li><button type="button" class="linkish" data-report="${r.as_of}">${r.name}</button></li>`
    ).join("");
  } catch (err) {
    els.reportList.innerHTML = `<li class="dim">${escapeHtml(err.message)}</li>`;
  }
}

async function showReport(asOf) {
  const data = await api(`/api/portfolio/reports/${asOf}`);
  renderRecalResult(data.json, data.markdown);
}

function renderRecalResult(summary, markdown) {
  if (summary) {
    const sp = summary.score_power || {};
    els.recalSummary.innerHTML = `
      <div class="score-pair">
        <div class="score-chip"><span>as of</span><strong>${summary.as_of}</strong></div>
        <div class="score-chip"><span>positions</span><strong>${summary.n_positions}</strong></div>
        <div class="score-chip"><span>Spearman</span><strong>${fmt(sp.spearman_score_fwd, 3)}</strong></div>
        <div class="score-chip"><span>Top-decile hit</span><strong>${sp.top_decile_hit_rate == null ? "—" : fmt(sp.top_decile_hit_rate * 100, 1) + "%"}</strong></div>
      </div>`;
    els.recalSuggestions.innerHTML = (summary.suggestions || [])
      .map((s) => `<p class="suggestion">• ${escapeHtml(s)}</p>`).join("");
  }
  els.recalMarkdown.textContent = markdown || "";
}

function openDrawer(ticker) {
  const row = findRow(ticker);
  if (!row) return;
  state.activeTicker = ticker;
  logger.info("drawer open", { ticker: row.ticker, sector: row.sector });

  const m = state.data.meta;
  els.drawerTicker.textContent = row.ticker;
  els.drawerSector.textContent = row.sector;
  els.drawerLead.textContent = "Evidence breakdown — descriptive modules only";

  const flags = [];
  if (row.portfolio && row.portfolio.held) {
    flags.push(`<span class="flag held">held position</span>`);
  }
  if (row.sector_low_confidence) {
    flags.push(`<span class="flag warn">sector low confidence (&lt;30 peers)</span>`);
  }
  flags.push(`<span class="flag">${row.social_badge} social</span>`);
  flags.push(`<span class="flag">c=${fmt(row.confidence_c, 2)} · n=${fmt(row.n, 0)}</span>`);
  if (row.value_coverage != null) {
    flags.push(`<span class="flag">value coverage ${fmt(row.value_coverage, 2)}</span>`);
  }
  if (row.value_pe_rung) {
    flags.push(`<span class="flag">P/E ${row.value_pe_rung}</span>`);
  }
  if (row.value_ev_rung) {
    flags.push(`<span class="flag">EV ${row.value_ev_rung}</span>`);
  }
  if (m.social_is_fixture || m.social_mode === "fixture") {
    flags.push(`<span class="flag warn">fixture attention</span>`);
  }
  els.drawerFlags.innerHTML = flags.join(" ");

  const held = row.portfolio && row.portfolio.held;
  const t = encodeURIComponent(row.ticker);
  els.drawerActions.innerHTML = held
    ? `<a class="primary" href="/trade?side=sell&ticker=${t}">Verkauf</a>
       <button type="button" class="ghost" data-action="journal">Journal note</button>`
    : `<a class="primary" href="/trade?side=buy&ticker=${t}">Kauf</a>
       <button type="button" class="ghost" data-action="watchlist">Watchlist</button>
       <button type="button" class="ghost" data-action="journal">Journal note</button>`;

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
    fact("Aktueller Kurs", fmtPx(row.last_price)),
  ].join("");

  els.drawerNote.innerHTML =
    "Composite Standing averages sector-relative V/Q/M. "
    + "Attention Tilt uses tanh + shrinkage around neutral 50 and cannot dominate the base. "
    + `<strong>${m.market_mode || "market"} · ${m.social_mode || "social"}</strong>. `
    + "Tagebuch und Holdings sind persönliche Notizen, keine Anlageberatung.";

  renderHolding(null);
  els.drawerDiary.innerHTML = "";
  loadDossier(row.ticker);

  renderPortfolioPanel(row);

  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
  els.scrim.hidden = false;
  requestAnimationFrame(() => {
    els.drawerBars.querySelectorAll(".bar-fill").forEach((el) => {
      el.style.width = el.dataset.width;
    });
  });
}

function renderPortfolioPanel(row) {
  const held = row.portfolio && row.portfolio.held;
  if (!held) {
    els.drawerPortfolio.classList.add("hidden");
    els.drawerScoreChart.innerHTML = "";
    els.drawerJournal.innerHTML = "";
    els.drawerPortfolioFacts.innerHTML = "";
    els.drawerScorePair.innerHTML = "";
    return;
  }
  els.drawerPortfolio.classList.remove("hidden");
  const p = row.portfolio;
  const bucket = p.drift_bucket || "n/a";
  const bucketClass = bucket === "n/a" ? "na" : bucket;
  const driftTxt = p.score_drift == null
    ? "—"
    : `${p.score_drift >= 0 ? "+" : ""}${Number(p.score_drift).toFixed(1)}`;
  els.drawerScorePair.innerHTML = `
    <div class="score-chip">
      <span>score@entry</span><strong>${fmt(p.score_at_entry)}</strong>
    </div>
    <div class="score-chip">
      <span>score_now</span><strong>${fmt(p.score_now)}</strong>
    </div>
    <div class="score-chip">
      <span>drift</span><strong class="drift drift-${bucketClass}">${driftTxt}</strong>
    </div>`;

  els.drawerPortfolioFacts.innerHTML = [
    fact("Kurs bei Einstieg", fmt(p.entry_price, 2)),
    fact("Stück", fmt(p.size, 2)),
    fact("Zielkurs", p.target_price != null ? fmt(p.target_price, 2) : "—"),
    fact("Stop", p.stop_price != null ? fmt(p.stop_price, 2) : "—"),
    fact("Opened (UTC)", p.open_ts || "—"),
  ].join("");
  els.drawerJournal.innerHTML = `<li class="dim">Loading journal…</li>`;
  els.drawerScoreChart.innerHTML = "";

  fetch(`/api/portfolio/position/${encodeURIComponent(row.ticker)}`)
    .then((r) => (r.ok ? r.json() : null))
    .then((detail) => {
      if (!detail) {
        els.drawerJournal.innerHTML = `<li class="dim">No position detail.</li>`;
        return;
      }
      const d = detail.distances || {};
      els.drawerPortfolioFacts.innerHTML = [
        fact("Kurs bei Einstieg", fmt(detail.position.entry_price, 2)),
        fact("Stück", fmt(detail.position.size, 2)),
        fact("Zielkurs", d.target_price != null ? fmt(d.target_price, 2) : "—"),
        fact("Stop", d.stop_price != null ? fmt(d.stop_price, 2) : "—"),
        fact("Dist → Zielkurs", d.dist_to_target_pct != null ? `${fmt(d.dist_to_target_pct, 1)}%` : "set mark price"),
        fact("Dist → Stop", d.dist_to_stop_pct != null ? `${fmt(d.dist_to_stop_pct, 1)}%` : "set mark price"),
        fact("Conviction", detail.thesis ? detail.thesis.conviction : "—"),
        fact("Falsifier", detail.thesis ? escapeHtml(detail.thesis.falsifier) : "—"),
      ].join("");
      drawScoreChart(detail.score_series || [], detail.journal || []);
      els.drawerJournal.innerHTML = (detail.journal || []).map((e) =>
        `<li><time datetime="${e.ts}">${formatLocal(e.ts)}</time>
         <span class="jtype">${e.entry_type}</span>
         <p>${escapeHtml(e.body)}</p></li>`
      ).join("") || `<li class="dim">No journal entries.</li>`;
    })
    .catch(() => {
      els.drawerJournal.innerHTML = `<li class="dim">Journal unavailable.</li>`;
    });
}

function drawScoreChart(series, journal) {
  const svg = els.drawerScoreChart;
  const w = 320;
  const h = 120;
  const pad = 16;
  if (!series.length) {
    svg.innerHTML = `<text x="${pad}" y="${h / 2}" class="chart-empty">No score history</text>`;
    return;
  }
  const ys = series.map((p) => Number(p.score));
  const minY = Math.min(...ys, 0);
  const maxY = Math.max(...ys, 100);
  const spanY = Math.max(1e-6, maxY - minY);
  const xAt = (i) => pad + (i / Math.max(1, series.length - 1)) * (w - 2 * pad);
  const yAt = (v) => h - pad - ((v - minY) / spanY) * (h - 2 * pad);
  const path = series.map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(p.score).toFixed(1)}`).join(" ");
  const journalMarks = (journal || []).map((e) => {
    const day = (e.ts || "").slice(0, 10);
    const idx = series.findIndex((p) => p.date === day);
    if (idx < 0) return "";
    return `<circle class="jmark" cx="${xAt(idx)}" cy="${yAt(series[idx].score)}" r="3.5">
      <title>${escapeHtml(e.entry_type)}: ${escapeHtml((e.body || "").slice(0, 80))}</title>
    </circle>`;
  }).join("");
  svg.innerHTML = `
    <path class="score-line" d="${path}" fill="none" />
    ${journalMarks}
    <text x="${pad}" y="12" class="chart-label">${fmt(maxY, 0)}</text>
    <text x="${pad}" y="${h - 4}" class="chart-label">${fmt(minY, 0)}</text>
  `;
}

function formatLocal(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
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

function field(name, label, attrs = "") {
  return `<label class="field"><span>${label}</span><input name="${name}" ${attrs} /></label>`;
}

function textarea(name, label, attrs = "") {
  return `<label class="field grow"><span>${label}</span><textarea name="${name}" rows="3" ${attrs}></textarea></label>`;
}

function openModal(kind, ticker = "") {
  state.modalKind = kind;
  state.activeTicker = ticker || state.activeTicker;
  els.modalError.textContent = "";
  const t = state.activeTicker || "";
  const titles = {
    buy: `Open position — ${t || "ticker"}`,
    sell: `Close position — ${t}`,
    journal: `Journal note — ${t || "ticker"}`,
    watchlist: `Watchlist — ${t || "ticker"}`,
  };
  const leads = {
    buy: "Requires a falsifier (≥20 chars). Thesis is frozen after open.",
    sell: "Exit note is required. Thesis stays immutable; this appends an exit_note.",
    journal: "Append-only update — does not edit the original thesis.",
    watchlist: "Watchlist thesis with falsifier. No position opened.",
  };
  els.modalTitle.textContent = titles[kind];
  els.modalLead.textContent = leads[kind];

  let html = "";
  if (kind === "buy") {
    html = `
      ${field("ticker", "Ticker", `value="${escapeHtml(t)}" required`)}
      ${field("price", "Entry price", 'type="number" step="any" min="0" required')}
      ${field("size", "Size", 'type="number" step="any" min="0" value="1" required')}
      ${field("target", "Target", 'type="number" step="any" min="0" required')}
      ${field("stop", "Stop", 'type="number" step="any" min="0" required')}
      ${field("horizon", "Horizon", 'value="90d" required')}
      ${field("conviction", "Conviction 1–5", 'type="number" min="1" max="5" value="3" required')}
      ${textarea("thesis", "Thesis / claim", "required")}
      ${textarea("mechanism", "Mechanism", "required")}
      ${textarea("falsifier", "Falsifier (≥20 chars)", "required minlength=\"20\"")}
      <button type="submit" class="primary">Open position</button>`;
  } else if (kind === "sell") {
    html = `
      ${field("ticker", "Ticker", `value="${escapeHtml(t)}" required readonly`)}
      ${field("price", "Close price", 'type="number" step="any" min="0" required')}
      <label class="field"><span>Reason</span>
        <select name="reason" required>
          <option value="target">target</option>
          <option value="stop">stop</option>
          <option value="thesis_broken">thesis_broken</option>
          <option value="rebalance">rebalance</option>
          <option value="manual">manual</option>
        </select>
      </label>
      ${textarea("note", "Exit note", "required")}
      <button type="submit" class="primary">Close position</button>`;
  } else if (kind === "journal") {
    html = `
      ${field("ticker", "Ticker", `value="${escapeHtml(t)}" required`)}
      ${textarea("note", "Note", "required")}
      <button type="submit" class="primary">Append note</button>`;
  } else if (kind === "watchlist") {
    html = `
      ${field("ticker", "Ticker", `value="${escapeHtml(t)}" required`)}
      ${textarea("thesis", "Thesis", "required")}
      ${textarea("falsifier", "Falsifier (≥20 chars)", "required minlength=\"20\"")}
      <button type="submit" class="primary">Add watchlist</button>`;
  }
  els.modalForm.innerHTML = html;
  els.modal.hidden = false;
  els.modalScrim.hidden = false;
}

function closeModal() {
  els.modal.hidden = true;
  els.modalScrim.hidden = true;
  state.modalKind = null;
  els.modalForm.innerHTML = "";
  els.modalError.textContent = "";
}

async function submitModal(e) {
  e.preventDefault();
  els.modalError.textContent = "";
  const fd = new FormData(els.modalForm);
  const kind = state.modalKind;
  const ticker = String(fd.get("ticker") || "").trim().toUpperCase();
  const row = findRow(ticker);
  const seed = snapshotSeedFromRow(row);
  try {
    if (kind === "buy") {
      await api("/api/portfolio/buy", {
        method: "POST",
        body: JSON.stringify({
          ticker,
          price: Number(fd.get("price")),
          size: Number(fd.get("size")),
          target: Number(fd.get("target")),
          stop: Number(fd.get("stop")),
          horizon: String(fd.get("horizon")),
          conviction: Number(fd.get("conviction")),
          thesis: String(fd.get("thesis")),
          mechanism: String(fd.get("mechanism")),
          falsifier: String(fd.get("falsifier")),
          snapshot: seed,
        }),
      });
      setStatus(`Opened ${ticker}`, "");
    } else if (kind === "sell") {
      await api("/api/portfolio/sell", {
        method: "POST",
        body: JSON.stringify({
          ticker,
          price: Number(fd.get("price")),
          reason: String(fd.get("reason")),
          note: String(fd.get("note")),
        }),
      });
      setStatus(`Closed ${ticker}`, "");
    } else if (kind === "journal") {
      await api("/api/portfolio/journal", {
        method: "POST",
        body: JSON.stringify({
          ticker,
          note: String(fd.get("note")),
          snapshot: seed,
        }),
      });
      setStatus(`Journal note on ${ticker}`, "");
    } else if (kind === "watchlist") {
      await api("/api/portfolio/watchlist", {
        method: "POST",
        body: JSON.stringify({
          ticker,
          thesis: String(fd.get("thesis")),
          falsifier: String(fd.get("falsifier")),
          snapshot: seed,
        }),
      });
      setStatus(`Watchlist ${ticker}`, "");
    }
    closeModal();
    closeDrawer();
    await loadSnapshot();
    if (state.view === "book") await loadBook();
  } catch (err) {
    els.modalError.textContent = err.message || String(err);
    logger.error("portfolio form failed", { kind, message: String(err.message || err) });
  }
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
    const data = await apiGet(`/api/holdings?${queryParams().toString()}`);
    state.held = new Set(data.held_tickers || []);
  } catch (err) {
    logger.warn("portfolio held load failed", { message: String(err) });
    state.held = new Set();
  }
}

async function loadDossier(ticker) {
  try {
    const data = await apiGet(`/api/holdings/${encodeURIComponent(ticker)}?${queryParams().toString()}`);
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
  // Placeholders until health boot finishes
  els.asOf.value = todayISO();
  els.recalAsOf.value = todayISO();
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
  els.bookBody.addEventListener("click", (e) => {
    const sell = e.target.closest("[data-sell]");
    if (sell) {
      openModal("sell", sell.dataset.sell);
      return;
    }
    const tr = e.target.closest("tr[data-ticker]");
    if (tr) {
      if (state.data) openDrawer(tr.dataset.ticker);
      else setView("standing");
    }
  });
  els.drawerActions.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    openModal(btn.dataset.action, state.activeTicker);
  });
  els.drawerClose.addEventListener("click", closeDrawer);
  els.scrim.addEventListener("click", closeDrawer);
  els.holdingForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const ticker = els.drawerTicker.textContent;
    try {
      await apiSend("/api/holdings", "POST", {
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
        kind: (els.diaryKind && els.diaryKind.value) || "observation",
        ...sourceBody(),
      });
      els.diaryComment.value = "";
      logger.info("diary appended", { ticker });
      await loadDossier(ticker);
    } catch (err) {
      setStatus(`Diary not saved: ${err.message}`, "error");
    }
  });
  els.modalClose.addEventListener("click", closeModal);
  els.modalScrim.addEventListener("click", closeModal);
  els.modalForm.addEventListener("submit", submitModal);
  els.btnWatchlist.addEventListener("click", () => openModal("watchlist", ""));
  els.btnJournal.addEventListener("click", () => openModal("journal", ""));
  els.btnRefreshBook.addEventListener("click", () => loadBook());
  els.btnRefreshReview.addEventListener("click", () => loadReview());
  els.reportList.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-report]");
    if (btn) showReport(btn.dataset.report).catch((err) => setStatus(err.message, "error"));
  });
  els.recalForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      setStatus("Running recalibrate…", "loading");
      const summary = await api("/api/portfolio/recalibrate", {
        method: "POST",
        body: JSON.stringify({
          window: els.recalWindow.value || "90d",
          min_hold: Number(els.recalMinHold.value || 30),
          as_of: els.recalAsOf.value || null,
        }),
      });
      const report = await api(summary.markdown_url);
      renderRecalResult(summary, report.markdown);
      await loadReportList();
      setStatus(`Recalibrate done · ${summary.n_positions} positions`, "");
    } catch (err) {
      setStatus(err.message, "error");
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModal();
      closeDrawer();
    }
    if (e.key === "/" && document.activeElement !== els.filter && els.modal.hidden) {
      e.preventDefault();
      els.filter.focus();
    }
  });
}

async function bootFromHealth() {
  try {
    const health = await api("/api/health");
    state.health = health;
    if (health.latest_snapshot_as_of) {
      els.asOf.value = health.latest_snapshot_as_of;
      els.recalAsOf.value = health.latest_snapshot_as_of;
    } else {
      els.asOf.value = todayISO();
      els.recalAsOf.value = todayISO();
    }
    if (health.default_market && [...els.market.options].some((o) => o.value === health.default_market)) {
      els.market.value = health.default_market;
    }
    if (health.default_social && [...els.social.options].some((o) => o.value === health.default_social)) {
      els.social.value = health.default_social;
    }
    if (health.portfolio_db_ok === false) {
      setStatus(
        `Portfolio DB not ready (${health.portfolio_db_error || "unknown"}). `
        + `Set STANDING_ROOT / writable artifacts. DB=${health.portfolio_db || "?"}`,
        "error",
      );
    } else if (!health.latest_snapshot_as_of && health.prefer_store) {
      setStatus(
        "No ingested snapshots found. Run: standing ingest --market live --social open "
        + "(or set Market/Attention to fixture for a demo).",
        "empty",
      );
    }
    logger.info("health boot", {
      root: health.root,
      latest_snapshot_as_of: health.latest_snapshot_as_of,
      portfolio_db_ok: health.portfolio_db_ok,
      snapshot_days: health.snapshot_days,
    });
  } catch (err) {
    logger.error("health boot failed", { message: String(err.message || err) });
    els.asOf.value = todayISO();
    els.recalAsOf.value = todayISO();
  }
}

function showError(err) {
  const msg = err && err.message ? err.message : String(err);
  logger.error("snapshot load failed", { message: msg });
  setStatus(`Failed to load: ${msg}`, "error");
  const row = `<tr class="state-row error"><td colspan="10">Failed to load: ${escapeHtml(msg)}</td></tr>`;
  els.standingBody.innerHTML = row;
  els.heatBody.innerHTML = row;
}

logger.info("desk boot");
bind();
bootFromHealth().then(() => loadSnapshot());
