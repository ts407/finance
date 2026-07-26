/**
 * Lightweight Standing UI logger.
 * Mirrors to console and batches events to POST /api/client-logs.
 */

const QUEUE_LIMIT = 40;
const FLUSH_MS = 800;

const state = {
  page: typeof document !== "undefined" ? document.title || location.pathname : "unknown",
  queue: [],
  timer: null,
  enabled: true,
};

function consoleMethod(level) {
  if (level === "debug") return console.debug.bind(console);
  if (level === "warn") return console.warn.bind(console);
  if (level === "error") return console.error.bind(console);
  return console.info.bind(console);
}

function enqueue(level, message, context) {
  if (!state.enabled) return;
  const entry = {
    level,
    message: String(message).slice(0, 2000),
    context: context && typeof context === "object" ? context : undefined,
    ts: new Date().toISOString(),
    page: state.page,
  };
  consoleMethod(level)(`[standing:${level}]`, message, context ?? "");
  state.queue.push(entry);
  if (state.queue.length > QUEUE_LIMIT) {
    state.queue.splice(0, state.queue.length - QUEUE_LIMIT);
  }
  scheduleFlush();
}

function scheduleFlush() {
  if (state.timer != null) return;
  state.timer = setTimeout(() => {
    state.timer = null;
    flush();
  }, FLUSH_MS);
}

async function flush() {
  if (!state.queue.length) return;
  const entries = state.queue.splice(0, state.queue.length);
  try {
    const res = await fetch("/api/client-logs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entries }),
      keepalive: true,
    });
    if (!res.ok) {
      console.warn("[standing:warn] client log flush failed", res.status);
    }
  } catch (err) {
    // Avoid recursive enqueue on transport failure.
    console.warn("[standing:warn] client log flush error", err);
  }
}

export const logger = {
  setPage(page) {
    state.page = page;
  },
  debug(message, context) {
    enqueue("debug", message, context);
  },
  info(message, context) {
    enqueue("info", message, context);
  },
  warn(message, context) {
    enqueue("warn", message, context);
  },
  error(message, context) {
    enqueue("error", message, context);
  },
  flush,
};

if (typeof window !== "undefined") {
  window.addEventListener("pagehide", () => {
    flush();
  });
  window.addEventListener("error", (event) => {
    enqueue("error", event.message || "window error", {
      source: event.filename,
      line: event.lineno,
      col: event.colno,
    });
  });
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    enqueue("error", "unhandledrejection", {
      reason: reason && reason.message ? reason.message : String(reason),
    });
  });
}

export default logger;
