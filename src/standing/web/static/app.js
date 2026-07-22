const state = {
  view: "standing",
  data: null,
};

const els = {
  asOf: document.getElementById("as-of"),
  filter: document.getElementById("filter"),
  sort: document.getElementById("sort"),
  reload: document.getElementById("reload"),
  standingBody: document.getElementById("standing-body"),
  heatBody: document.getElementById("heat-body"),
  boardStanding: document.getElementById("board-standing"),
  boardHeat: document.getElementById("board-heat"),
  drawer: document.getElementById("drawer"),
  scrim: document.getElementById("scrim"),
  drawerClose: document.getElementById("drawer-close"),
  drawerTicker: document.getElementById("drawer-ticker"),
  drawerSector: document.getElementById("drawer-sector"),
  drawerBars: document.getElementById("drawer-bars"),
  drawerFacts: document.getElementById("drawer-facts"),
  metaAsof: document.getElementById("meta-asof"),
  metaUniverse: document.getElementById("meta-universe"),
  metaN: document.getElementById("meta-n"),
  metaPlaceholder: document.getElementById("meta-placeholder"),
  footMethod: document.getElementById("foot-method"),
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

async function loadSnapshot() {
  const params = new URLSearchParams({
    as_of: els.asOf.value || todayISO(),
    sort: els.sort.value,
  });
  if (els.filter.value.trim()) params.set("q", els.filter.value.trim());
  const res = await fetch(`/api/snapshot?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  state.data = await res.json();
  renderMeta();
  renderTables();
}

function renderMeta() {
  const m = state.data.meta;
  els.metaAsof.textContent = m.as_of;
  els.metaUniverse.textContent = m.universe_id;
  els.metaN.textContent = String(m.n_names);
  els.metaPlaceholder.textContent = m.placeholder ? "placeholder" : "frozen";
  els.footMethod.textContent = `${m.score_kind} · ${m.methodology_version}`;
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
  els.standingBody.innerHTML = standings.map(standingRow).join("");
  els.heatBody.innerHTML = heat.map(heatRow).join("");
  // trigger heat bar animation on next frame
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

  els.drawerTicker.textContent = row.ticker;
  els.drawerSector.textContent = row.sector;
  els.drawerBars.innerHTML = [
    bar("Value", row.value, "v"),
    bar("Quality", row.quality, "q"),
    bar("Momentum", row.momentum, "m"),
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
  ].join("");

  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
  els.scrim.hidden = false;
  requestAnimationFrame(() => {
    els.drawerBars.querySelectorAll(".bar-fill").forEach((el) => {
      const w = el.dataset.width;
      el.style.width = w;
    });
  });
}

function bar(label, value, cls, raw = false) {
  const width = raw ? Math.max(0, Math.min(100, value)) : Math.max(0, Math.min(100, value));
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

function bind() {
  els.asOf.value = "2026-07-22";
  els.reload.addEventListener("click", () => loadSnapshot().catch(showError));
  els.asOf.addEventListener("change", () => loadSnapshot().catch(showError));
  els.sort.addEventListener("change", () => loadSnapshot().catch(showError));
  let timer;
  els.filter.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => loadSnapshot().catch(showError), 180);
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
  });
}

function showError(err) {
  console.error(err);
  els.standingBody.innerHTML = `<tr><td colspan="9">Failed to load: ${err.message}</td></tr>`;
}

bind();
loadSnapshot().catch(showError);
