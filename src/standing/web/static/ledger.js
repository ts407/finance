/**
 * Shared helpers for Desk ↔ Portfolio ↔ Diary.
 * Personal ledger is local (STANDING_DATA_DIR/diary); never a scoring input.
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

export const KIND_LABELS = {
  observation: "Beobachtung",
  note: "Notiz",
  thesis_update: "These",
  buy: "Kauf",
  add: "Nachkauf",
  close: "Verkauf",
  entwurf: "Entwurf",
};

export function fmtPct(n, digits = 1) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const sign = Number(n) > 0 ? "+" : "";
  return `${sign}${(Number(n) * 100).toFixed(digits)}%`;
}

export function relPct(to, from) {
  const a = Number(to);
  const b = Number(from);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
  return a / b - 1;
}

export function rewardRisk(entry, target, stop) {
  const e = Number(entry);
  const t = Number(target);
  const s = Number(stop);
  if (![e, t, s].every(Number.isFinite) || e <= s) return null;
  return (t - e) / (e - s);
}

export function geometryMarks({ last, entry, target, stop, shares, pnlAbs, pnlPct, finalStanding }) {
  const upside = relPct(target, last);
  const upsideEntry = relPct(target, entry);
  const downside = relPct(stop, last);
  const rr = rewardRisk(entry, target, stop);
  return {
    last_price: last,
    entry_price: entry,
    target_price: target,
    stop_price: stop,
    shares,
    pnl_abs: pnlAbs,
    pnl_pct: pnlPct,
    upside_pct: upside,
    upside_from_entry_pct: upsideEntry,
    downside_pct: downside,
    reward_risk: rr,
    final_standing: finalStanding,
  };
}

export function geometryGrid(marks) {
  const m = marks || {};
  const rr = m.reward_risk;
  const pairs = [
    ["Aktueller Kurs", fmtPx(m.last_price), ""],
    ["Kurs bei Einstieg", fmtPx(m.entry_price), ""],
    ["Zielkurs", fmtPx(m.target_price), ""],
    ["Stop", fmtPx(m.stop_price), ""],
    ["Upside Potential", fmtPct(m.upside_pct), pnlClass(m.upside_pct)],
    ["These-Upside", fmtPct(m.upside_from_entry_pct), pnlClass(m.upside_from_entry_pct)],
    ["Dist → Stop", fmtPct(m.downside_pct), pnlClass(m.downside_pct)],
    ["Chance/Risiko", rr == null || Number.isNaN(Number(rr)) ? "—" : `${fmt(rr, 2)}×`, ""],
    ["Stück", m.shares == null ? "—" : fmt(m.shares, 4), ""],
    ["P&L", fmtPnl(m.pnl_abs, m.pnl_pct), pnlClass(m.pnl_abs)],
  ];
  if (m.final_standing != null) {
    pairs.push(["Final", fmt(m.final_standing), ""]);
  }
  return pairs
    .map(
      ([label, value, cls]) =>
        `<div><dt>${escapeHtml(label)}</dt><dd class="${cls}">${escapeHtml(value)}</dd></div>`,
    )
    .join("");
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
    ["Aktueller Kurs", fmtPx(s.last_price)],
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
  const marks = entry.marks || {};
  const last = marks.last_price != null ? marks.last_price : scores.last_price;
  const final = marks.final_standing != null ? marks.final_standing : scores.final_standing;
  const pnl = marks.pnl_abs;
  const kindLabel = KIND_LABELS[entry.kind] || entry.kind;
  const entwurf = entry.entwurf || {};
  const attachment = entwurf.attachment || {};
  const attachmentUrl = attachment.name ? `/api/trade/entwurf/file/${encodeURIComponent(attachment.name)}` : "";
  const funds = entwurf.fundamentals || marks.fundamentals || {};
  const fundBits = [];
  if (funds.pe_ttm != null) fundBits.push(`KGV ${escapeHtml(fmt(funds.pe_ttm))}`);
  if (funds.pb != null) fundBits.push(`KBV ${escapeHtml(fmt(funds.pb, 2))}`);
  if (funds.ev_ebitda != null) fundBits.push(`EV/EBITDA ${escapeHtml(fmt(funds.ev_ebitda))}`);
  const sourceLine = entwurf.source
    ? `<p class="note-meta">Quelle ${escapeHtml(entwurf.source)}${entwurf.url ? ` · ${escapeHtml(entwurf.url)}` : ""}</p>`
    : "";
  const image = attachmentUrl
    ? `<figure class="entwurf-figure"><img src="${escapeHtml(attachmentUrl)}" alt="" /></figure>`
    : "";
  return `<article class="note-card" data-ticker="${escapeHtml(entry.ticker)}">
    <header>
      <a class="ticker-link" href="/diary?ticker=${encodeURIComponent(entry.ticker)}" data-filter-ticker="${escapeHtml(entry.ticker)}">${escapeHtml(entry.ticker)}</a>
      <span class="badge ${escapeHtml(entry.kind)}">${escapeHtml(kindLabel)}</span>
      <time>${escapeHtml((entry.created_utc || "").replace("T", " ").slice(0, 19))} UTC</time>
    </header>
    <p>${escapeHtml(entry.comment)}</p>
    ${sourceLine}
    ${image}
    <dl class="mark-grid">
      ${geometryGrid({
        last_price: last,
        entry_price: marks.entry_price,
        target_price: marks.target_price,
        stop_price: marks.stop_price,
        shares: marks.shares,
        pnl_abs: pnl,
        pnl_pct: marks.pnl_pct,
        upside_pct: marks.upside_pct,
        upside_from_entry_pct: marks.upside_from_entry_pct,
        downside_pct: marks.downside_pct,
        reward_risk: marks.reward_risk,
        final_standing: final,
      })}
    </dl>
    <p class="note-meta">
      V ${escapeHtml(fmt(scores.value))} · Q ${escapeHtml(fmt(scores.quality))} · M ${escapeHtml(fmt(scores.momentum))}
      ${fundBits.length ? ` · ${fundBits.join(" · ")}` : ""}
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
  <a href="/trade">Trade</a>
  <a href="/diary">Diary</a>
  <a href="/methodology">Methodology</a>
`;
