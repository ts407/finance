import { logger } from "./logger.js";
import {
  KIND_LABELS,
  apiGet,
  apiSend,
  diaryCard,
  escapeHtml,
  fillSourceControls,
  sourceParams,
  storeSource,
} from "./ledger.js";

logger.setPage("diary");

const FILTER_KEYS = ["ticker", "q", "since", "until", "kind"];

const els = {
  asOf: document.getElementById("as-of"),
  market: document.getElementById("market"),
  social: document.getElementById("social"),
  ticker: document.getElementById("ticker"),
  kind: document.getElementById("kind"),
  q: document.getElementById("q"),
  since: document.getElementById("since"),
  until: document.getElementById("until"),
  reload: document.getElementById("reload"),
  status: document.getElementById("status-line"),
  entries: document.getElementById("entries"),
  chips: document.getElementById("ticker-chips"),
  compose: document.getElementById("compose"),
  newTicker: document.getElementById("new-ticker"),
  newKind: document.getElementById("new-kind"),
  newComment: document.getElementById("new-comment"),
  exportCsv: document.getElementById("export-csv"),
  exportJson: document.getElementById("export-json"),
};

function filterParams() {
  const p = new URLSearchParams();
  FILTER_KEYS.forEach((key) => {
    const el = els[key];
    const value = el && el.value ? el.value.trim() : "";
    if (value) p.set(key, value);
  });
  return p;
}

function applyUrlFilters() {
  const url = new URL(location.href);
  FILTER_KEYS.forEach((key) => {
    const value = url.searchParams.get(key);
    if (value && els[key]) els[key].value = value;
  });
  if (url.searchParams.get("ticker") && els.newTicker && !els.newTicker.value) {
    els.newTicker.value = url.searchParams.get("ticker");
  }
}

function syncUrl() {
  const next = new URL(location.href);
  FILTER_KEYS.forEach((key) => next.searchParams.delete(key));
  filterParams().forEach((value, key) => next.searchParams.set(key, value));
  history.replaceState({}, "", `${next.pathname}${next.search}${next.hash}`);
}

function syncExports() {
  const q = filterParams().toString();
  const suffix = q ? `?${q}` : "";
  if (els.exportCsv) els.exportCsv.href = `/api/diary.csv${suffix}`;
  if (els.exportJson) els.exportJson.href = `/api/diary.json${suffix}`;
}

function formatDay(day) {
  if (!day) return "Ohne Datum";
  const parsed = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return day;
  return parsed.toLocaleDateString("de-DE", {
    weekday: "short",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function groupByDay(rows) {
  const groups = [];
  let current = null;
  for (const row of rows) {
    const day = String(row.created_utc || "").slice(0, 10);
    if (!current || current.day !== day) {
      current = { day, rows: [] };
      groups.push(current);
    }
    current.rows.push(row);
  }
  return groups;
}

function renderEntries(rows) {
  if (!rows.length) {
    els.entries.innerHTML = `<p class="muted">No notes yet. Write from here or from the desk drawer.</p>`;
    return;
  }
  els.entries.innerHTML = groupByDay(rows)
    .map(
      (group) => `
      <section class="day-group">
        <h2>${escapeHtml(formatDay(group.day))}</h2>
        ${group.rows.map(diaryCard).join("")}
      </section>`,
    )
    .join("");
}

function renderChips(corpus, selected) {
  const counts = (corpus && corpus.ticker_counts) || {};
  const tickers = Object.keys(counts).sort();
  if (!tickers.length) {
    els.chips.innerHTML = "";
    return;
  }
  const allOn = selected ? "" : " is-on";
  els.chips.innerHTML = [
    `<button type="button" class="chip${allOn}" data-ticker="">Alle</button>`,
    ...tickers.map((ticker) => {
      const on = selected === ticker ? " is-on" : "";
      return `<button type="button" class="chip${on}" data-ticker="${escapeHtml(ticker)}">${escapeHtml(ticker)} <span>${counts[ticker]}</span></button>`;
    }),
  ].join("");
}

function statusText(summary) {
  const s = summary || {};
  const kinds = s.kinds || {};
  const kindBits = Object.entries(kinds)
    .sort((a, b) => b[1] - a[1])
    .map(([kind, n]) => `${KIND_LABELS[kind] || kind} ${n}`)
    .join(" · ");
  const base = `${s.n_entries || 0} notes · ${s.n_tickers || 0} tickers`;
  return kindBits ? `${base} · ${kindBits}` : base;
}

function setTickerFilter(ticker) {
  els.ticker.value = ticker || "";
  if (ticker) els.newTicker.value = ticker;
  load();
}

async function load() {
  const p = filterParams();
  syncUrl();
  syncExports();
  els.status.textContent = "Loading diary…";
  try {
    const data = await apiGet(`/api/diary?${p.toString()}`);
    const rows = data.entries || [];
    renderEntries(rows);
    renderChips(data.corpus || data.summary || {}, els.ticker.value.trim().toUpperCase());
    els.status.textContent = statusText(data.summary);
    logger.info("diary load ok", { n: rows.length });
  } catch (err) {
    els.status.textContent = `Failed: ${err.message}`;
    logger.error("diary load failed", { message: err.message });
  }
}

fillSourceControls(els);
applyUrlFilters();

els.reload.addEventListener("click", load);
FILTER_KEYS.forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", load);
});
els.chips.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-ticker]");
  if (!chip) return;
  const next = chip.dataset.ticker || "";
  setTickerFilter(els.ticker.value.trim().toUpperCase() === next ? "" : next);
});
els.entries.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-filter-ticker]");
  if (!btn || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
  e.preventDefault();
  setTickerFilter(btn.dataset.filterTicker);
});
els.compose.addEventListener("submit", async (e) => {
  e.preventDefault();
  storeSource({ as_of: els.asOf.value, market: els.market.value, social: els.social.value });
  const src = sourceParams({
    as_of: els.asOf.value,
    market: els.market.value,
    social: els.social.value,
  });
  try {
    await apiSend("/api/diary", "POST", {
      ticker: els.newTicker.value,
      comment: els.newComment.value,
      kind: els.newKind.value || "observation",
      as_of: src.get("as_of"),
      market: src.get("market"),
      social: src.get("social"),
    });
    els.newComment.value = "";
    els.ticker.value = els.newTicker.value;
    await load();
  } catch (err) {
    els.status.textContent = `Not saved: ${err.message}`;
  }
});

logger.info("diary boot");
load();
