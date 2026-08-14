import { logger } from "./logger.js";
import {
  apiGet,
  apiSend,
  escapeHtml,
  factsHtml,
  fillSourceControls,
  fmt,
  fmtPct,
  fmtPx,
  geometryGrid,
  geometryMarks,
  pnlClass,
  scoreFacts,
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
  btnSnap: document.getElementById("btn-snap"),
  snapCard: document.getElementById("snap-card"),
  snapEmpty: document.getElementById("snap-empty"),
  snapFacts: document.getElementById("snap-facts"),
  snapMeta: document.getElementById("snap-meta"),
  entwurfForm: document.getElementById("entwurf-form"),
  entwurfUrl: document.getElementById("entwurf-url"),
  entwurfText: document.getElementById("entwurf-text"),
  entwurfPng: document.getElementById("entwurf-png"),
  entwurfTicker: document.getElementById("entwurf-ticker"),
  entwurfUrlField: document.getElementById("entwurf-url-field"),
  entwurfTextField: document.getElementById("entwurf-text-field"),
  entwurfPngField: document.getElementById("entwurf-png-field"),
  entwurfCard: document.getElementById("entwurf-card"),
  entwurfEmpty: document.getElementById("entwurf-empty"),
  entwurfBody: document.getElementById("entwurf-body"),
  entwurfSourceMeta: document.getElementById("entwurf-source-meta"),
  entwurfFigure: document.getElementById("entwurf-figure"),
  entwurfImage: document.getElementById("entwurf-image"),
  entwurfFundamentals: document.getElementById("entwurf-fundamentals"),
  entwurfThesis: document.getElementById("entwurf-thesis"),
  entwurfReason: document.getElementById("entwurf-reason"),
  entwurfMechanism: document.getElementById("entwurf-mechanism"),
  entwurfFalsifier: document.getElementById("entwurf-falsifier"),
  btnEntwurfApply: document.getElementById("btn-entwurf-apply"),
};

const state = {
  side: "buy",
  book: [],
  last: null,
  thesis: null,
  snap: null,
  pendingSnap: null,
  snapSource: "",
  stale: false,
  entwurfSource: "url",
  entwurf: null,
};

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

function sourceKey() {
  const src = sourceBody();
  return `${src.as_of || ""}|${src.market || ""}|${src.social || ""}`;
}

function currentTicker() {
  const sell = state.side === "sell" ? els.sellTicker.value : "";
  return (sell || els.buyTicker.value || els.entwurfTicker.value || "").trim().toUpperCase();
}

function setEntwurfSource(source) {
  const next = source === "text" || source === "png" ? source : "url";
  state.entwurfSource = next;
  ["url", "text", "png"].forEach((key) => {
    const tab = document.getElementById(`entwurf-tab-${key}`);
    if (tab) {
      tab.classList.toggle("active", key === next);
      tab.setAttribute("aria-selected", String(key === next));
    }
  });
  if (els.entwurfUrlField) els.entwurfUrlField.classList.toggle("hidden", next !== "url");
  if (els.entwurfTextField) els.entwurfTextField.classList.toggle("hidden", next !== "text");
  if (els.entwurfPngField) els.entwurfPngField.classList.toggle("hidden", next !== "png");
}

function renderEntwurf(result) {
  state.entwurf = result || null;
  const ready = Boolean(result && result.draft);
  els.entwurfEmpty.classList.toggle("hidden", ready);
  els.entwurfBody.classList.toggle("hidden", !ready);
  els.entwurfCard.classList.toggle("is-ready", ready);
  if (!ready) {
    if (!els.entwurfEmpty.dataset.kind) {
      els.entwurfEmpty.textContent = "Link, Text oder PNG eingeben — persönlicher Entwurf, keine Empfehlung.";
    }
    els.entwurfFundamentals.innerHTML = "";
    els.entwurfSourceMeta.textContent = "";
    els.entwurfFigure.classList.add("hidden");
    els.entwurfImage.removeAttribute("src");
    return;
  }
  els.entwurfEmpty.dataset.kind = "";
  const draft = result.draft || {};
  const sourceLabel = result.source === "url" ? "Link" : result.source === "png" ? "PNG" : "Text";
  const bits = [`Quelle: ${sourceLabel}`];
  if (result.ticker) bits.push(result.ticker);
  if (result.title) bits.push(result.title);
  if (result.url) bits.push(result.url);
  els.entwurfSourceMeta.textContent = bits.join(" · ");
  els.entwurfThesis.value = draft.thesis || "";
  els.entwurfReason.value = draft.buy_reason || "";
  els.entwurfMechanism.value = draft.mechanism || "";
  els.entwurfFalsifier.value = draft.falsifier || "";
  if (result.ticker && result.ticker !== "ENTWURF" && !els.entwurfTicker.value) {
    els.entwurfTicker.value = result.ticker;
  }
  const display = result.fundamentals_display || [];
  els.entwurfFundamentals.innerHTML = display.length
    ? factsHtml(display)
    : "";
  if (result.attachment_url) {
    els.entwurfImage.src = result.attachment_url;
    els.entwurfFigure.classList.remove("hidden");
  } else {
    els.entwurfFigure.classList.add("hidden");
    els.entwurfImage.removeAttribute("src");
  }
}

function fileToPngPayload(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("PNG fehlt"));
      return;
    }
    const type = (file.type || "").toLowerCase();
    if (type && type !== "image/png") {
      reject(new Error("Nur PNG"));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("PNG konnte nicht gelesen werden"));
    reader.readAsDataURL(file);
  });
}

function applyEntwurfToKauf() {
  const apply = (state.entwurf && state.entwurf.apply) || {};
  const original = (state.entwurf && state.entwurf.draft) || {};
  const ticker = (els.entwurfTicker.value || apply.ticker || "").trim().toUpperCase();
  setSide("buy");
  if (ticker && ticker !== "ENTWURF") els.buyTicker.value = ticker;
  if (els.entwurfThesis.value) els.buyThesis.value = els.entwurfThesis.value;
  if (els.entwurfReason.value) els.buyReason.value = els.entwurfReason.value;
  if (els.entwurfMechanism.value) els.buyMechanism.value = els.entwurfMechanism.value;
  const edited = (els.entwurfFalsifier.value || "").trim();
  const originalFalsifier = original.falsifier || "";
  if (edited && edited !== originalFalsifier) {
    els.buyFalsifier.value = edited;
  } else if (apply.falsifier) {
    els.buyFalsifier.value = apply.falsifier;
  }
  setStatus("Entwurf in Kauf-Formular übernommen — noch nicht gebucht.");
  logger.info("trade entwurf applied", { ticker: ticker || null });
  if (ticker && ticker !== "ENTWURF") loadTicker(ticker);
}

async function developEntwurf(e) {
  e.preventDefault();
  const ticker = (els.entwurfTicker.value || els.buyTicker.value || "").trim().toUpperCase();
  const body = {
    source: state.entwurfSource,
    ticker: ticker || null,
    ...sourceBody(),
    ...(state.snap && (!ticker || (state.snap.scores && state.snap.scores.ticker) === ticker)
      ? { score_snap: state.snap }
      : {}),
  };
  try {
    if (state.entwurfSource === "url") {
      body.url = (els.entwurfUrl.value || "").trim();
      if (!body.url) throw new Error("Link fehlt");
    } else if (state.entwurfSource === "text") {
      body.text = (els.entwurfText.value || "").trim();
      if (!body.text) throw new Error("Text fehlt");
    } else {
      const file = els.entwurfPng.files && els.entwurfPng.files[0];
      body.image_b64 = await fileToPngPayload(file);
      body.filename = file.name;
    }
    setStatus("Entwurf wird entwickelt…");
    const result = await apiSend("/api/trade/entwurf", "POST", body);
    renderEntwurf(result);
    if (result.ticker && result.ticker !== "ENTWURF") {
      els.entwurfTicker.value = result.ticker;
    }
    setStatus(`Entwurf ${result.ticker || ""} · nicht gebucht, nicht score-wirksam`);
    logger.info("trade entwurf ok", { ticker: result.ticker, source: result.source, id: result.id });
  } catch (err) {
    els.entwurfEmpty.classList.remove("hidden");
    els.entwurfBody.classList.add("hidden");
    els.entwurfEmpty.dataset.kind = "error";
    els.entwurfEmpty.textContent = err.message;
    setStatus(`Entwurf fehlgeschlagen: ${err.message}`, "error");
    logger.warn("trade entwurf failed", { message: err.message });
  }
}

function fmtUtc(iso) {
  if (!iso) return "—";
  return `${String(iso).replace("T", " ").replace("Z", "").slice(0, 19)} UTC`;
}

function renderSnap() {
  const snap = state.snap;
  els.snapCard.classList.toggle("is-frozen", Boolean(snap) && !state.stale);
  els.snapCard.classList.toggle("is-stale", Boolean(snap) && state.stale);
  if (!snap) {
    els.snapEmpty.classList.remove("hidden");
    els.snapFacts.innerHTML = "";
    els.snapMeta.textContent = "";
    if (!els.snapEmpty.textContent || els.snapEmpty.dataset.kind !== "error") {
      els.snapEmpty.dataset.kind = "";
      els.snapEmpty.textContent = "Load a ticker, then freeze the desk score.";
    }
    return;
  }
  els.snapEmpty.classList.add("hidden");
  els.snapEmpty.dataset.kind = "";
  els.snapFacts.innerHTML = factsHtml(scoreFacts(snap));
  const stale = state.stale ? " Source changed — snap again to freeze." : "";
  els.snapMeta.textContent =
    `Frozen ${fmtUtc(snap.captured_utc)} · as of ${snap.as_of || "—"} · ${snap.methodology_version || "—"} · ${snap.market_mode || "—"}/${snap.social_mode || "—"}.${stale}`;
}

async function snapScore({ recapture = false } = {}) {
  const ticker = currentTicker();
  if (!ticker) {
    state.snap = null;
    state.pendingSnap = null;
    state.stale = false;
    els.snapEmpty.dataset.kind = "";
    renderSnap();
    return null;
  }
  const body = { ticker, ...sourceBody() };
  if (!recapture && state.pendingSnap) body.score_snap = state.pendingSnap;
  try {
    setStatus(`Freezing score ${ticker}…`);
    const result = await apiSend("/api/trade/snap", "POST", body);
    state.snap = result.snapshot;
    state.pendingSnap = result.snapshot;
    state.snapSource = sourceKey();
    state.stale = false;
    renderSnap();
    setStatus(`Score frozen ${ticker} · ${fmtUtc(result.snapshot && result.snapshot.captured_utc)}`);
    logger.info("trade snap ok", { ticker, snapshot_id: result.snapshot_id });
    return result;
  } catch (err) {
    state.snap = null;
    state.stale = false;
    els.snapEmpty.classList.remove("hidden");
    els.snapEmpty.dataset.kind = "error";
    els.snapEmpty.textContent = err.message;
    els.snapFacts.innerHTML = "";
    els.snapMeta.textContent = "";
    els.snapCard.classList.remove("is-frozen", "is-stale");
    setStatus(`Score snap failed: ${err.message}`, "error");
    logger.warn("trade snap failed", { ticker, message: err.message });
    return null;
  }
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
    state.snap = null;
    state.pendingSnap = null;
    state.stale = false;
    renderSnap();
    return;
  }
  try {
    const src = sourceParams({
      as_of: els.asOf.value,
      market: els.market.value,
      social: els.social.value,
    });
    const detail = await apiGet(`/api/ticker/${encodeURIComponent(key)}?${src.toString()}`);
    state.pendingSnap = detail.snapshot || null;
    renderQuote(detail);
    applyQuoteToForms(detail);
    if (els.entwurfTicker && !els.entwurfTicker.value) els.entwurfTicker.value = key;
    logger.info("trade quote", { ticker: key, last: detail.row && detail.row.last_price });
    await snapScore({ recapture: false });
  } catch (err) {
    els.quote.innerHTML = `<div><dt>Quote</dt><dd>${escapeHtml(err.message)}</dd></div>`;
    state.snap = null;
    state.pendingSnap = null;
    state.stale = false;
    renderSnap();
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
  if (els.entwurfTicker) els.entwurfTicker.value = els.buyTicker.value;
}
setSide((boot.searchParams.get("side") || "buy").toLowerCase());
setEntwurfSource("url");

els.tabBuy.addEventListener("click", () => setSide("buy"));
els.tabSell.addEventListener("click", () => setSide("sell"));
els.buyTicker.addEventListener("change", () => {
  if (els.entwurfTicker && !els.entwurfTicker.value) els.entwurfTicker.value = els.buyTicker.value.trim().toUpperCase();
  loadTicker(els.buyTicker.value);
});
els.buyTicker.addEventListener("blur", () => loadTicker(els.buyTicker.value));
els.btnSnap.addEventListener("click", () => snapScore({ recapture: true }));
document.querySelectorAll("[data-entwurf-source]").forEach((tab) => {
  tab.addEventListener("click", () => setEntwurfSource(tab.dataset.entwurfSource));
});
if (els.entwurfForm) els.entwurfForm.addEventListener("submit", developEntwurf);
if (els.btnEntwurfApply) els.btnEntwurfApply.addEventListener("click", applyEntwurfToKauf);
["as-of", "market", "social"].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("change", () => {
    if (state.snap && state.snapSource !== sourceKey()) {
      state.stale = true;
      renderSnap();
    }
    const t = currentTicker();
    if (t) loadTicker(t);
  });
});
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
      ...(state.snap ? { score_snap: state.snap } : {}),
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
      ...(state.snap ? { score_snap: state.snap } : {}),
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
