import { logger } from "./logger.js";

logger.setPage("desk");

const state = {
  view: "standing",
  data: null,
  loading: false,
  sectorsPopulated: false,
};

const els = {
  asOf: document.getElementById("as-of"),
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
  metaAsof: document.getElementById("meta-asof"),
  metaUniverse: document.getElementById("meta-universe"),
  metaN: document.getElementById("meta-n"),
  metaPlaceholder: document.getElementById("meta-placeholder"),
  footMethod: document.getElementById("foot-method"),
  footPosture: document.getElementById("foot-posture"),
};

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function fmt(n, digits = 1) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}

function tiltClass(v) {
  return Number(v) >= 0 ? "tilt-pos" : "tilt-neg";
}

function queryParams() {
  const params = new URLSearchParams({
    as_of: els.asOf.value || todayISO(),
    sort: els.sort.value,
    preset: els.preset.value,
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
    renderMeta();
    populateSectors();
    renderTables();
    const n = state.data.standings.length;
    logger.info("snapshot load ok", {
      n,
      universe: state.data.meta.universe_id,
      as_of: state.data.meta.as_of,
    });
    setStatus(
      n === 0
        ? "No rows match this preset / filter."
        : `${n} names · preset ${els.preset.value}`,
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
  els.metaUniverse.textContent = m.universe_id;
  els.metaN.textContent = String(m.n_names);
  els.metaPlaceholder.textContent = m.placeholder ? "placeholder" : "frozen";
  els.footMethod.textContent = `${m.score_kind} · ${m.methodology_version}`;
  els.footPosture.textContent = `${m.market_provider} · ${m.social_provider} · live social later`;
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
  return `<tr data-ticker="${row.ticker}">
    <td class="ticker">${row.ticker}</td>
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
  return `<tr data-ticker="${row.ticker}">
    <td class="ticker">${row.ticker}</td>
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
  ].join("");

  els.drawerNote.innerHTML =
    "Composite Standing averages sector-relative V/Q/M. "
    + "Attention Tilt uses tanh + shrinkage around neutral 50 and cannot dominate the base. "
    + "<strong>Fixture social · live later.</strong> Not investment advice.";

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

function bind() {
  els.asOf.value = "2026-07-22";
  els.reload.addEventListener("click", () => loadSnapshot());
  els.exportCsv.addEventListener("click", exportCsv);
  els.asOf.addEventListener("change", () => loadSnapshot());
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
