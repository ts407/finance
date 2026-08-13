import { logger } from "./logger.js";
import {
  apiGet,
  apiSend,
  diaryCard,
  fillSourceControls,
  sourceParams,
  storeSource,
} from "./ledger.js";

logger.setPage("diary");

const els = {
  asOf: document.getElementById("as-of"),
  market: document.getElementById("market"),
  social: document.getElementById("social"),
  ticker: document.getElementById("ticker"),
  q: document.getElementById("q"),
  since: document.getElementById("since"),
  until: document.getElementById("until"),
  reload: document.getElementById("reload"),
  status: document.getElementById("status-line"),
  entries: document.getElementById("entries"),
  compose: document.getElementById("compose"),
  newTicker: document.getElementById("new-ticker"),
  newComment: document.getElementById("new-comment"),
};

function filterParams() {
  const p = new URLSearchParams();
  if (els.ticker.value.trim()) p.set("ticker", els.ticker.value.trim());
  if (els.q.value.trim()) p.set("q", els.q.value.trim());
  if (els.since.value) p.set("since", els.since.value);
  if (els.until.value) p.set("until", els.until.value);
  return p;
}

async function load() {
  const p = filterParams();
  els.status.textContent = "Loading diary…";
  try {
    const data = await apiGet(`/api/diary?${p.toString()}`);
    const rows = data.entries || [];
    els.entries.innerHTML = rows.map(diaryCard).join("")
      || `<p class="muted">No notes yet. Write from here or from the desk drawer.</p>`;
    const s = data.summary || {};
    els.status.textContent = `${s.n_entries || 0} notes · ${s.n_tickers || 0} tickers`;
    logger.info("diary load ok", { n: rows.length });
  } catch (err) {
    els.status.textContent = `Failed: ${err.message}`;
    logger.error("diary load failed", { message: err.message });
  }
}

fillSourceControls(els);
const url = new URL(location.href);
if (url.searchParams.get("ticker")) {
  els.ticker.value = url.searchParams.get("ticker");
  els.newTicker.value = url.searchParams.get("ticker");
}

els.reload.addEventListener("click", load);
["ticker", "q", "since", "until"].forEach((id) => {
  document.getElementById(id).addEventListener("change", load);
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
      kind: "observation",
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
