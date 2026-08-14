import { logger } from "./logger.js";
import {
  apiGet,
  apiSend,
  escapeHtml,
  fillSourceControls,
  fmt,
  fmtPct,
  fmtPx,
  geometryGrid,
  geometryMarks,
  pnlClass,
  sourceParams,
  storeSource,
} from "./ledger.js";

logger.setPage("trade");

const els = {
  asOf: document.getElementById("as-of"),
  market: document.getElementById("market"),
  social: document.getElementById("social"),
  status: document.getElementById("status-line"),
  tabBuy: document.getElementById("tab-buy"),
  tabSell: document.getElementById("tab-sell"),
  formTitle: document.getElementById("form-title"),
  formLead: document.getElementById("form-lead"),
  buyForm: document.getElementById("buy-form"),
  sellForm: document.getElementById("sell-form"),
  buyTicker: document.getElementById("buy-ticker"),
  buySize: document.getElementById("buy-size"),
  buyPrice: document.getElementById("buy-price"),
  buyLast: document.getElementById("buy-last"),
  buyTarget: document.getElementById("buy-target"),
  buyStop: document.getElementById("buy-stop"),
  buyHorizon: document.getElementById("buy-horizon"),
  buyConviction: document.getElementById("buy-conviction"),
  buyReason: document.getElementById("buy-reason"),
  buyThesis: document.getElementById("buy-thesis"),
  buyMechanism: document.getElementById("buy-mechanism"),
  buyFalsifier: document.getElementById("buy-falsifier"),
  sellTicker: document.getElementById("sell-ticker"),
  sellLast: document.getElementById("sell-last"),
  sellEntry: document.getElementById("sell-entry"),
  sellPrice: document.getElementById("sell-price"),
  sellTarget: document.getElementById("sell-target"),
  sellStop: document.getElementById("sell-stop"),
  sellReason: document.getElementById("sell-reason"),
  sellNote: document.getElementById("sell-note"),
  geo: document.getElementById("geo"),
  quote: document.getElementById("quote"),
  bookBody: document.getElementById("book-body"),
};

const state = { side: "buy", book: [], last: null, thesis: null };

function sourceBody() {
  storeSource({ as_of: els.asOf.value, market: els.market.value, social: els.social.value });
  const src = sourceParams({
    as_of: els.asOf.value,
    market: els.market.value,
    social: els.social.value,
  });
  return {
    as_of: src.get("as_of"),
    market: src.get("market"),
    social: src.get("social"),
  };
}

function setSide(side) {
  state.side = side === "sell" ? "sell" : "buy";
  const sell = state.side === "sell";
  els.tabBuy.classList.toggle("active", !sell);
  els.tabSell.classList.toggle("active", sell);
  els.tabBuy.setAttribute("aria-selected", String(!sell));
  els.tabSell.setAttribute("aria-selected", String(sell));
  els.buyForm.classList.toggle("hidden", sell);
  els.sellForm.classList.toggle("hidden", !sell);
  els.formTitle.textContent = sell ? "Verkauf" : "Kauf";
  els.formLead.textContent = sell
    ? "Close a book position with Verkaufskurs, Grund, and an append-only exit note."
    : "Open a position: Aktueller Kurs, Stück, Einstieg, Zielkurs, Upside Potential, Stop.";
  refreshGeometry();
  const url = new URL(location.href);
  url.searchParams.set("side", state.side);
  history.replaceState({}, "", `${url.pathname}${url.search}`);
}

function setStatus(text, kind = "") {
  els.status.textContent = text;
  els.status.classList.toggle("error", kind === "error");
}

function numField(el) {
  if (!el) return null;
  const n = Number(el.value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function refreshGeometry() {
  const last = state.last;
  let marks;
  if (state.side === "sell") {
    const pos = state.book.find((p) => p.ticker === (els.sellTicker.value || "").toUpperCase());
    const entry = pos ? pos.entry_price : null;
    const target = pos && pos.target_price != null ? pos.target_price : state.thesis && state.thesis.target_price;
    const stop = pos && pos.stop_price != null ? pos.stop_price : state.thesis && state.thesis.stop_price;
    const sellPx = numField(els.sellPrice) || last;
    const pnlPct = entry && sellPx ? sellPx / entry - 1 : null;
    const shares = pos ? pos.size : null;
    const pnlAbs = shares != null && entry != null && sellPx != null ? shares * (sellPx - entry) : null;
    marks = geometryMarks({
      last: last || sellPx,
      entry,
      target,
      stop,
      shares,
      pnlAbs,
      pnlPct,
    });
  } else {
    const entry = numField(els.buyPrice) || last;
    const target = numField(els.buyTarget);
    const stop = numField(els.buyStop);
    const shares = numField(els.buySize);
    const pnlPct = entry && last ? last / entry - 1 : null;
    const pnlAbs = shares != null && entry != null && last != null ? shares * (last - entry) : null;
    marks = geometryMarks({
      last,
      entry,
      target,
      stop,
      shares,
      pnlAbs,
      pnlPct,
    });
  }
  els.geo.innerHTML = geometryGrid(marks);
}

function renderQuote(detail) {
  if (!detail || !detail.row) {
    els.quote.innerHTML = "";
    return;
  }
  const row = detail.row;
  const book = detail.book || {};
  const pos = book.position || {};
  const thesis = book.thesis || {};
  const last = row.last_price;
  const upside = book.distances && book.distances.dist_to_target_pct != null
    ? book.distances.dist_to_target_pct / 100
    : (thesis.target_price != null && last ? thesis.target_price / last - 1 : null);
  els.quote.innerHTML = [
    ["Ticker", row.ticker],
    ["Aktueller Kurs", fmtPx(last)],
    ["Zielkurs", fmtPx(thesis.target_price)],
    ["Upside Potential", fmtPct(upside)],
    ["Stop", fmtPx(thesis.stop_price)],
    ["Final", fmt(row.final_standing)],
    ["V / Q / M", `${fmt(row.value)} / ${fmt(row.quality)} / ${fmt(row.momentum)}`],
    ["Held", detail.held || pos.ticker ? "yes" : "no"],
    ["Kurs bei Einstieg", fmtPx(pos.entry_price)],
  ]
    .map(
      ([label, value]) =>
        `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value ?? "—"))}</dd></div>`,
    )
    .join("");
}

function applyQuoteToForms(detail) {
  const row = (detail && detail.row) || {};
  const book = (detail && detail.book) || {};
  const pos = book.position || {};
  const thesis = book.thesis || {};
  const last = row.last_price;
  state.last = last != null && Number.isFinite(Number(last)) ? Number(last) : null;
  state.thesis = thesis;
  if (last != null) {
    els.buyLast.value = fmtPx(last);
    els.sellLast.value = fmtPx(last);
    if (!els.buyPrice.value) els.buyPrice.value = Number(last);
    if (!els.sellPrice.value) els.sellPrice.value = Number(last);
  } else {
    els.buyLast.value = "—";
    els.sellLast.value = "—";
  }
  els.sellEntry.value = pos.entry_price != null ? fmtPx(pos.entry_price) : "—";
  els.sellTarget.value = thesis.target_price != null ? fmtPx(thesis.target_price) : "—";
  els.sellStop.value = thesis.stop_price != null ? fmtPx(thesis.stop_price) : "—";
  if (!els.buyTarget.value && thesis.target_price != null) els.buyTarget.value = Number(thesis.target_price);
  if (!els.buyStop.value && thesis.stop_price != null) els.buyStop.value = Number(thesis.stop_price);
  refreshGeometry();
}

async function loadTicker(ticker) {
  const key = (ticker || "").trim().toUpperCase();
  if (!key) {
    els.quote.innerHTML = "";
    return;
  }
  try {
    const src = sourceParams({
      as_of: els.asOf.value,
      market: els.market.value,
      social: els.social.value,
    });
    const detail = await apiGet(`/api/ticker/${encodeURIComponent(key)}?${src.toString()}`);
    renderQuote(detail);
    applyQuoteToForms(detail);
    logger.info("trade quote", { ticker: key, last: detail.row && detail.row.last_price });
  } catch (err) {
    els.quote.innerHTML = `<div><dt>Quote</dt><dd>${escapeHtml(err.message)}</dd></div>`;
    logger.warn("trade quote failed", { ticker: key, message: err.message });
  }
}

function renderBook(positions) {
  state.book = positions || [];
  const selected = els.sellTicker.value;
  els.sellTicker.innerHTML =
    `<option value="">Open position…</option>` +
    state.book
      .map(
        (p) =>
          `<option value="${escapeHtml(p.ticker)}" ${p.ticker === selected ? "selected" : ""}>${escapeHtml(p.ticker)}</option>`,
      )
      .join("");
  if (!state.book.length) {
    els.bookBody.innerHTML = `<tr class="state-row"><td colspan="8">No open positions. Book a Kauf first.</td></tr>`;
    return;
  }
  els.bookBody.innerHTML = state.book
    .map((p) => {
      const pnl = p.pnl_pct;
      const cls = pnlClass(pnl == null ? null : pnl);
      const upside = p.dist_to_target_pct;
      const down = p.dist_to_stop_pct;
      return `<tr data-ticker="${escapeHtml(p.ticker)}">
        <td class="ticker">${escapeHtml(p.ticker)}</td>
        <td class="num">${escapeHtml(fmtPx(p.entry_price))}</td>
        <td class="num">${escapeHtml(fmtPx(p.now_px))}</td>
        <td class="num">${escapeHtml(fmtPx(p.target_price))}</td>
        <td class="num ${pnlClass(upside == null ? null : upside)}">${upside == null ? "—" : fmtPct(upside / 100)}</td>
        <td class="num">${down == null ? "—" : fmtPct(down / 100)}</td>
        <td class="num ${cls}">${pnl == null ? "—" : `${fmt(pnl, 1)}%`}</td>
        <td><button type="button" class="ghost tiny" data-sell="${escapeHtml(p.ticker)}">Verkauf</button></td>
      </tr>`;
    })
    .join("");
}

async function loadBook() {
  try {
    const data = await apiGet("/api/portfolio");
    renderBook(data.positions || []);
  } catch (err) {
    els.bookBody.innerHTML = `<tr class="state-row error"><td colspan="8">${escapeHtml(err.message)}</td></tr>`;
  }
}

function pickSell(ticker) {
  setSide("sell");
  els.sellTicker.value = ticker;
  els.buyTicker.value = ticker;
  const pos = state.book.find((p) => p.ticker === ticker);
  if (pos) {
    els.sellEntry.value = fmtPx(pos.entry_price);
    els.sellTarget.value = pos.target_price != null ? fmtPx(pos.target_price) : "—";
    els.sellStop.value = pos.stop_price != null ? fmtPx(pos.stop_price) : "—";
    if (pos.now_px != null) {
      state.last = Number(pos.now_px);
      els.sellLast.value = fmtPx(pos.now_px);
      if (!els.sellPrice.value) els.sellPrice.value = Number(pos.now_px);
    }
  }
  refreshGeometry();
  loadTicker(ticker);
}

fillSourceControls(els);
const boot = new URL(location.href);
if (boot.searchParams.get("ticker")) {
  els.buyTicker.value = boot.searchParams.get("ticker").toUpperCase();
}
setSide((boot.searchParams.get("side") || "buy").toLowerCase());

els.tabBuy.addEventListener("click", () => setSide("buy"));
els.tabSell.addEventListener("click", () => setSide("sell"));
els.buyTicker.addEventListener("change", () => loadTicker(els.buyTicker.value));
els.buyTicker.addEventListener("blur", () => loadTicker(els.buyTicker.value));
["buy-price", "buy-target", "buy-stop", "buy-size", "sell-price"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("input", refreshGeometry);
});
els.sellTicker.addEventListener("change", () => {
  const t = els.sellTicker.value;
  if (t) pickSell(t);
});
els.bookBody.addEventListener("click", (e) => {
  const sell = e.target.closest("[data-sell]");
  if (sell) {
    pickSell(sell.dataset.sell);
    return;
  }
  const tr = e.target.closest("tr[data-ticker]");
  if (tr) pickSell(tr.dataset.ticker);
});

els.buyForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const ticker = els.buyTicker.value.trim().toUpperCase();
  setStatus(`Booking Kauf ${ticker}…`);
  try {
    const result = await apiSend("/api/trade/buy", "POST", {
      ticker,
      price: Number(els.buyPrice.value),
      size: Number(els.buySize.value),
      target: Number(els.buyTarget.value),
      stop: Number(els.buyStop.value),
      horizon: els.buyHorizon.value,
      conviction: Number(els.buyConviction.value),
      buy_reason: els.buyReason.value,
      thesis: els.buyThesis.value,
      mechanism: els.buyMechanism.value,
      falsifier: els.buyFalsifier.value,
      ...sourceBody(),
    });
    els.buyThesis.value = "";
    els.buyReason.value = "";
    els.buyMechanism.value = "";
    els.buyFalsifier.value = "";
    const warn = result.holdings_error ? ` (diary: ${result.holdings_error})` : "";
    setStatus(`Kauf ${result.ticker} @ ${fmtPx(result.entry_price)} · ${fmt(result.size, 4)} Stück${warn}`);
    logger.info("trade buy ok", { ticker: result.ticker, position_id: result.position_id });
    await loadBook();
    await loadTicker(ticker);
  } catch (err) {
    setStatus(`Kauf not saved: ${err.message}`, "error");
    logger.error("trade buy failed", { message: err.message });
  }
});

els.sellForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const ticker = els.sellTicker.value.trim().toUpperCase();
  setStatus(`Booking Verkauf ${ticker}…`);
  try {
    const result = await apiSend("/api/trade/sell", "POST", {
      ticker,
      price: Number(els.sellPrice.value),
      reason: els.sellReason.value,
      note: els.sellNote.value,
      ...sourceBody(),
    });
    els.sellNote.value = "";
    els.sellPrice.value = "";
    const warn = result.holdings_error ? ` (diary: ${result.holdings_error})` : "";
    setStatus(
      `Verkauf ${result.ticker} @ ${fmtPx(result.close_price)} · ${result.close_reason} · P&L ${fmt(result.pnl_pct, 1)}%${warn}`,
    );
    logger.info("trade sell ok", { ticker: result.ticker, reason: result.close_reason });
    await loadBook();
  } catch (err) {
    setStatus(`Verkauf not saved: ${err.message}`, "error");
    logger.error("trade sell failed", { message: err.message });
  }
});

logger.info("trade boot");
loadBook().then(() => {
  const ticker = els.buyTicker.value.trim();
  if (ticker) {
    if (state.side === "sell") pickSell(ticker);
    else loadTicker(ticker);
  }
});
