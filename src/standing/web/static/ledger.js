/**
 * Shared helpers for Desk ↔ Portfolio ↔ Diary.
 * Personal ledger is local (artifacts/desk); never a scoring input.
 */

export function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export function sourceParams(overrides = {}) {
  const stored = readStoredSource();
  const params = new URLSearchParams({
    as_of: overrides.as_of || stored.as_of || todayISO(),
    market: overrides.market || stored.market || "live",
    social: overrides.social || stored.social || "open",
    history_days: "14",
  });
  return params;
}

export function storeSource({ as_of, market, social }) {
  try {
    localStorage.setItem(
      "standing.deskSource",
      JSON.stringify({ as_of, market, social }),
    );
  } catch {
    /* ignore quota */
  }
}

export function readStoredSource() {
  try {
    return JSON.parse(localStorage.getItem("standing.deskSource") || "{}") || {};
  } catch {
    return {};
  }
}

export function fmt(n, digits = 1) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}

export function fmtPx(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtPnl(abs, pct) {
  if (abs == null || Number.isNaN(Number(abs))) return "—";
  const sign = Number(abs) > 0 ? "+" : "";
  const pctTxt = pct == null ? "" : ` (${sign}${(Number(pct) * 100).toFixed(1)}%)`;
  return `${sign}${fmtPx(abs)}${pctTxt}`;
}

export function pnlClass(abs) {
  if (abs == null || Number.isNaN(Number(abs)) || Number(abs) === 0) return "";
  return Number(abs) > 0 ? "pnl-pos" : "pnl-neg";
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export async function apiSend(path, method, body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    throw new Error(typeof detail === "string" ? detail : res.statusText);
  }
  return res.json();
}

export function scoreFacts(snapshot) {
  const s = (snapshot && snapshot.scores) || snapshot || {};
  return [
    ["Final", fmt(s.final_standing)],
    ["V / Q / M", `${fmt(s.value)} / ${fmt(s.quality)} / ${fmt(s.momentum)}`],
    ["Composite", fmt(s.composite_standing)],
    ["Tilt", fmt(s.attention_tilt, 2)],
    ["Kurs", fmtPx(s.last_price)],
    ["n / c", `${fmt(s.n, 0)} / ${fmt(s.confidence_c, 2)}`],
    ["Neg share", fmt(s.neg_share, 2)],
    ["Social", s.social_badge || "—"],
  ];
}

export function factsHtml(pairs) {
  return pairs
    .map(
      ([label, value]) =>
        `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`,
    )
    .join("");
}

export function diaryCard(entry) {
  const snap = entry.snapshot || {};
  const scores = snap.scores || {};
  return `<article class="note-card" data-ticker="${escapeHtml(entry.ticker)}">
    <header>
      <strong>${escapeHtml(entry.ticker)}</strong>
      <span class="badge ${escapeHtml(entry.kind)}">${escapeHtml(entry.kind)}</span>
      <time>${escapeHtml((entry.created_utc || "").replace("T", " ").slice(0, 19))} UTC</time>
    </header>
    <p>${escapeHtml(entry.comment)}</p>
    <p class="note-meta">
      Final ${fmt(scores.final_standing)} · Kurs ${fmtPx(scores.last_price)}
      · ${escapeHtml(snap.methodology_version || "—")}
      · ${escapeHtml(snap.as_of || "—")}
    </p>
  </article>`;
}

export function fillSourceControls(els) {
  const stored = readStoredSource();
  if (els.asOf && !els.asOf.value) els.asOf.value = stored.as_of || todayISO();
  if (els.market && stored.market) els.market.value = stored.market;
  if (els.social && stored.social) els.social.value = stored.social;
}

export const NAV = `
  <a href="/">Desk</a>
  <a href="/portfolio">Portfolio</a>
  <a href="/diary">Diary</a>
  <a href="/methodology">Methodology</a>
`;
