// Parses, validates and aggregates community regression reports filed as
// GitHub issues with the regression-report form. No dependencies, no I/O.
//
// Issue bodies are untrusted input. Nothing in this module evaluates or
// renders them: the JSON block is parsed with JSON.parse, checked against a
// strict schema (exact keys, fixed vocabularies, anchored patterns, bounded
// sizes), and only the validated fields are copied into the aggregate. The
// site escapes every value again when it renders.

export const LABEL = "regression-report";
export const SHARE_SCHEMA = "nerf-watch-share/1";

/** GitHub caps issue bodies at 65,536 characters. */
export const MAX_BODY_CHARS = 65536;
/** The JSON block itself. nerf-watch keeps it far below this. */
export const MAX_JSON_CHARS = 16384;
export const MAX_FINDINGS = 20;
export const MAX_AGENTS = 10;
/** Issue links listed per aggregate row. */
export const MAX_ISSUE_LINKS = 20;

/** nerf-watch detector id -> signal, and the trigger each detector produces. */
export const DETECTORS = {
  "newInput-shift": { signal: "tokens", trigger: "version", effect: "ratio" },
  "newInput-drift": { signal: "tokens", trigger: "time", effect: "ratio" },
  "firstTurnPrompt-shift": { signal: "tokens", trigger: "version", effect: "ratio" },
  "cacheCreation-shift": { signal: "cache-writes", trigger: "version", effect: "ratio" },
  "cacheCreation-drift": { signal: "cache-writes", trigger: "time", effect: "ratio" },
  "cacheHitRate-shift": { signal: "cache-hit-rate", trigger: "version", effect: "pp" },
  "cacheHitRate-drift": { signal: "cache-hit-rate", trigger: "time", effect: "pp" },
  "toolErrorRate-shift": { signal: "tool-errors", trigger: "version", effect: "pp" },
  "toolErrorRate-drift": { signal: "tool-errors", trigger: "time", effect: "pp" },
  "contextWindow-shift": { signal: "context-shrink", trigger: "version", effect: "ratio" },
  "contextWindow-drift": { signal: "context-shrink", trigger: "time", effect: "ratio" },
  "effort-drop": { signal: "effort-drop", trigger: "version", effect: "levels" },
  "model-mismatch": { signal: "model-reroute", trigger: "event", effect: "share" },
  "hidden-model": { signal: "other", trigger: "event", effect: null },
};

/** Unit of the effect size per signal. Every detector of one signal uses the same unit. */
export const SIGNAL_EFFECT_UNIT = Object.fromEntries(Object.values(DETECTORS).map((d) => [d.signal, d.effect]));

const AGENT = /^[a-z][a-z0-9-]{0,31}$/;
const VERSION = /^(?:[0-9][0-9A-Za-z.+-]{0,39}|custom-version)$/;
const MODEL = /^[A-Za-z0-9][A-Za-z0-9_.\-\[\]]{0,79}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISSUE_URL = /^https:\/\/github\.com\/[A-Za-z0-9-]{1,39}\/[A-Za-z0-9._-]{1,100}\/issues\/[1-9]\d{0,8}$/;

/** Generic checks applied to every string, on top of each field's own pattern. */
const SUSPICIOUS = [
  ["a path", /[\/\\~]|^[A-Za-z]:|\.\./],
  ["an email address", /@/],
  ["a URL", /:\/\/|^www\./i],
  ["markup", /[<>&"'`]/],
  ["a session id", /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i],
  ["a long hex id", /[0-9a-f]{24,}/i],
  ["a long numeric id", /\d{10,}/],
  ["whitespace or control characters", /[\s\u0000-\u001f\u007f-\u009f\u2028\u2029]/],
];

class Invalid extends Error {}

const fail = (path, msg) => {
  throw new Invalid(`${path}: ${msg}`);
};

function isPlainObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype;
}

function exactKeys(v, path, keys) {
  if (!isPlainObject(v)) fail(path, "expected an object");
  const got = Object.keys(v);
  for (const k of got) if (!keys.includes(k)) fail(path, `unexpected key`);
  for (const k of keys) if (!Object.prototype.hasOwnProperty.call(v, k)) fail(path, `missing key "${k}"`);
}

function str(v, path, re) {
  if (typeof v !== "string") fail(path, "expected a string");
  if (v.length === 0 || v.length > 80) fail(path, "string length out of range");
  if (v !== SHARE_SCHEMA) for (const [what, bad] of SUSPICIOUS) if (bad.test(v)) fail(path, `looks like ${what}`);
  if (re && !re.test(v)) fail(path, "does not match the expected format");
  return v;
}

function oneOf(v, path, values) {
  if (typeof v !== "string" || !values.includes(v)) fail(path, "not an allowed value");
  return v;
}

function num(v, path, { min = 0, max = 1e9, int = false } = {}) {
  if (typeof v !== "number" || !Number.isFinite(v)) fail(path, "expected a finite number");
  if (int && !Number.isInteger(v)) fail(path, "expected an integer");
  if (v < min || v > max) fail(path, "number out of range");
  return v;
}

function date(v, path, now) {
  str(v, path, DATE);
  const t = Date.parse(`${v}T00:00:00Z`);
  if (!Number.isFinite(t) || new Date(t).toISOString().slice(0, 10) !== v) fail(path, "not a calendar date");
  if (t < Date.UTC(2023, 0, 1) || t > now + 2 * 86400000) fail(path, "date out of range");
  return v;
}

const dateOrNull = (v, path, now) => (v === null ? null : date(v, path, now));

function side(v, path, now, { fraction = false, level = false } = {}) {
  exactKeys(v, path, ["value", "samples", "from", "to"]);
  const value = num(v.value, `${path}.value`, fraction ? { max: 1 } : level ? { max: 10, int: true } : {});
  const samples = num(v.samples, `${path}.samples`, { int: true });
  const from = dateOrNull(v.from, `${path}.from`, now);
  const to = dateOrNull(v.to, `${path}.to`, now);
  if (from && to && from > to) fail(path, "from is after to");
  return { value, samples, from, to };
}

function finding(f, path, now) {
  exactKeys(f, path, ["detector", "signal", "severity", "trigger", "agent", "model", "servedModel", "cliBefore", "cliAfter", "before", "after"]);
  const detector = oneOf(f.detector, `${path}.detector`, Object.keys(DETECTORS));
  const spec = DETECTORS[detector];
  if (f.signal !== spec.signal) fail(`${path}.signal`, "does not match the detector");
  if (f.trigger !== spec.trigger) fail(`${path}.trigger`, "does not match the detector");
  const severity = oneOf(f.severity, `${path}.severity`, ["warn", "alert"]);
  const agent = str(f.agent, `${path}.agent`, AGENT);
  const model = str(f.model, `${path}.model`, MODEL);
  const servedModel = f.servedModel === null ? null : str(f.servedModel, `${path}.servedModel`, MODEL);
  if (detector === "model-mismatch" && servedModel === null) fail(`${path}.servedModel`, "required for model-mismatch");
  if (detector !== "model-mismatch" && servedModel !== null) fail(`${path}.servedModel`, "only allowed for model-mismatch");
  const cliBefore = f.cliBefore === null ? null : str(f.cliBefore, `${path}.cliBefore`, VERSION);
  const cliAfter = str(f.cliAfter, `${path}.cliAfter`, VERSION);
  const fraction = spec.effect === "pp" || spec.effect === "share";
  const level = spec.effect === "levels";
  let before = null;
  if (spec.trigger === "event") {
    if (f.before !== null) fail(`${path}.before`, "must be null for this detector");
  } else {
    before = side(f.before, `${path}.before`, now, { fraction, level });
  }
  const after = side(f.after, `${path}.after`, now, { fraction, level });
  return { detector, signal: spec.signal, severity, trigger: spec.trigger, agent, model, servedModel, cliBefore, cliAfter, before, after };
}

/**
 * Strictly validates a nerf-watch share payload. Returns a fresh object built
 * only from validated fields, or throws with the reason.
 */
export function validatePayload(doc, now = Date.now()) {
  exactKeys(doc, "(root)", ["schema", "nerfWatchVersion", "window", "agents", "findings"]);
  if (doc.schema !== SHARE_SCHEMA) fail("schema", `expected "${SHARE_SCHEMA}"`);
  const nerfWatchVersion = str(doc.nerfWatchVersion, "nerfWatchVersion", VERSION);
  exactKeys(doc.window, "window", ["from", "to"]);
  const window = { from: dateOrNull(doc.window.from, "window.from", now), to: dateOrNull(doc.window.to, "window.to", now) };
  if (!Array.isArray(doc.agents) || doc.agents.length > MAX_AGENTS) fail("agents", `expected an array of at most ${MAX_AGENTS}`);
  const agents = doc.agents.map((a, i) => {
    exactKeys(a, `agents[${i}]`, ["id", "sessions", "turns"]);
    return { id: str(a.id, `agents[${i}].id`, AGENT), sessions: num(a.sessions, `agents[${i}].sessions`, { int: true }), turns: num(a.turns, `agents[${i}].turns`, { int: true }) };
  });
  if (!Array.isArray(doc.findings) || doc.findings.length === 0 || doc.findings.length > MAX_FINDINGS) {
    fail("findings", `expected 1 to ${MAX_FINDINGS} findings`);
  }
  const findings = doc.findings.map((f, i) => finding(f, `findings[${i}]`, now));
  return { schema: SHARE_SCHEMA, nerfWatchVersion, window, agents, findings };
}

/**
 * Finds the JSON block in an issue body produced by the regression-report
 * form: the first fenced code block whose content starts with "{". Returns
 * the raw text, or throws.
 */
export function extractJsonBlock(body) {
  if (typeof body !== "string" || body.length === 0) fail("body", "empty");
  if (body.length > MAX_BODY_CHARS) fail("body", "too large");
  const fence = /^[ \t]{0,3}(`{3,}|~{3,})[ \t]*([A-Za-z0-9_-]*)[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]{0,3}\1[ \t]*$/gm;
  let m;
  let blocks = 0;
  while ((m = fence.exec(body)) !== null) {
    if (++blocks > 20) break;
    const lang = m[2].toLowerCase();
    if (lang && lang !== "json") continue;
    const text = m[3].trim();
    if (!text.startsWith("{")) continue;
    if (text.length > MAX_JSON_CHARS) fail("report", "JSON block too large");
    return text;
  }
  fail("report", "no JSON block found");
}

/**
 * Parses one issue from the GitHub REST API. Returns
 * { ok: true, report } or { ok: false, number, reason }. The reason never
 * echoes issue content.
 */
export function parseIssue(issue, { repoUrl, now = Date.now() } = {}) {
  const number = Number.isInteger(issue?.number) && issue.number > 0 ? issue.number : null;
  try {
    if (!number) fail("issue", "no number");
    if (issue.pull_request) fail("issue", "is a pull request");
    if (issue.state !== "open") fail("issue", "not open");
    const labels = Array.isArray(issue.labels) ? issue.labels.map((l) => (typeof l === "string" ? l : l?.name)) : [];
    if (!labels.includes(LABEL)) fail("issue", `missing the ${LABEL} label`);
    const author = issue.user && typeof issue.user.id === "number" ? `id:${issue.user.id}` : typeof issue.user?.login === "string" ? `login:${issue.user.login.toLowerCase()}` : null;
    if (!author) fail("issue", "no author");
    const created = typeof issue.created_at === "string" ? Date.parse(issue.created_at) : NaN;
    if (!Number.isFinite(created)) fail("issue", "no creation time");
    const text = extractJsonBlock(issue.body);
    let doc;
    try {
      doc = JSON.parse(text);
    } catch {
      fail("report", "not valid JSON");
    }
    const payload = validatePayload(doc, now);
    const url = `${repoUrl}/issues/${number}`;
    if (!ISSUE_URL.test(url)) fail("issue", "unexpected repository URL");
    return { ok: true, report: { number, url, author, created, payload } };
  } catch (e) {
    if (e instanceof Invalid) return { ok: false, number, reason: e.message };
    throw e;
  }
}

export function median(xs) {
  if (!xs.length) return null;
  const s = xs.slice().sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Effect size of one finding in its signal's unit, or null when it has none. */
export function effectOf(f) {
  const unit = DETECTORS[f.detector]?.effect;
  if (unit === "ratio") return f.before && f.before.value > 0 ? f.after.value / f.before.value : null;
  if (unit === "pp" || unit === "levels") return f.before ? f.after.value - f.before.value : null;
  if (unit === "share") return f.after.value;
  return null;
}

const round = (x, d = 4) => (x === null ? null : Number(x.toFixed(d)));

function compareVersions(a, b) {
  const pa = a.split(/[.+-]/);
  const pb = b.split(/[.+-]/);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] ?? "";
    const y = pb[i] ?? "";
    const nx = /^\d+$/.test(x) ? Number(x) : NaN;
    const ny = /^\d+$/.test(y) ? Number(y) : NaN;
    const c = !Number.isNaN(nx) && !Number.isNaN(ny) ? nx - ny : x.localeCompare(y);
    if (c) return c;
  }
  return 0;
}

/**
 * Groups findings by (agent, CLI version, model, signal). A row counts
 * independent reports: distinct issue authors. When one author filed several
 * issues for the same row, only their newest one counts.
 */
export function aggregate(reports) {
  const rows = new Map();
  for (const r of reports) {
    const seen = new Set();
    for (const f of r.payload.findings) {
      const key = [f.agent, f.cliAfter, f.model, f.signal].join("\u0000");
      if (seen.has(key)) continue; // one vote per issue per row
      seen.add(key);
      let row = rows.get(key);
      if (!row) rows.set(key, (row = { agent: f.agent, cli_version: f.cliAfter, model: f.model, signal: f.signal, byAuthor: new Map(), issues: new Map() }));
      row.issues.set(r.number, r.url);
      const prev = row.byAuthor.get(r.author);
      if (!prev || r.created > prev.created) row.byAuthor.set(r.author, { created: r.created, finding: f });
    }
  }
  const out = [];
  for (const row of rows.values()) {
    const votes = [...row.byAuthor.values()].map((v) => v.finding);
    const effects = votes.map(effectOf).filter((x) => x !== null && Number.isFinite(x));
    const starts = votes.map((f) => f.after.from).filter(Boolean).sort();
    const ends = votes.map((f) => f.after.to).filter(Boolean).sort();
    const before = [...new Set(votes.map((f) => f.cliBefore).filter((v) => v && v !== row.cli_version))].sort(compareVersions);
    const served = [...new Set(votes.map((f) => f.servedModel).filter(Boolean))].sort();
    out.push({
      agent: row.agent,
      cli_version: row.cli_version,
      cli_before: before.slice(0, 5),
      model: row.model,
      served_models: served.slice(0, 5),
      signal: row.signal,
      reports: votes.length,
      alerts: votes.filter((f) => f.severity === "alert").length,
      effect_median: round(median(effects)),
      effect_unit: SIGNAL_EFFECT_UNIT[row.signal] ?? null,
      first_seen: starts[0] ?? null,
      last_seen: ends[ends.length - 1] ?? null,
      issues: [...row.issues.entries()]
        .sort((a, b) => a[0] - b[0])
        .slice(0, MAX_ISSUE_LINKS)
        .map(([number, url]) => ({ number, url })),
    });
  }
  return out.sort(
    (a, b) =>
      b.reports - a.reports ||
      a.agent.localeCompare(b.agent) ||
      compareVersions(b.cli_version, a.cli_version) ||
      a.model.localeCompare(b.model) ||
      a.signal.localeCompare(b.signal),
  );
}

/**
 * The whole pipeline over a list of API issues. Returns the aggregate rows
 * and a per-issue log of what was accepted or rejected (numbers and reasons
 * only, never content).
 */
export function processIssues(issues, { repoUrl, now = Date.now() } = {}) {
  const accepted = [];
  const rejected = [];
  for (const issue of issues) {
    const r = parseIssue(issue, { repoUrl, now });
    if (r.ok) accepted.push(r.report);
    else rejected.push({ number: r.number, reason: r.reason });
  }
  return { aggregates: aggregate(accepted), accepted: accepted.map((r) => r.number), rejected };
}

/** Serializes data/regressions.json. Keeps hand-reviewed `reports` as they are. */
export function serialize(existing, aggregates) {
  const reports = existing && Array.isArray(existing.reports) ? existing.reports : [];
  return JSON.stringify({ reports, aggregates }, null, 2) + "\n";
}
