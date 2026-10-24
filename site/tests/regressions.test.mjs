// Parser, validator and aggregator for community regression reports, run on
// synthetic issue bodies, including hostile ones. Run with `npm test`.

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  aggregate,
  effectOf,
  extractJsonBlock,
  MAX_BODY_CHARS,
  MAX_JSON_CHARS,
  parseIssue,
  processIssues,
  serialize,
  validatePayload,
} from "../scripts/lib/regressions.mjs";
import { loadAll } from "../scripts/lib/data.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_URL = "https://github.com/Abelo9996/open-agent-lab";
const NOW = Date.UTC(2026, 9, 3, 12);

function cacheWrites(over = {}) {
  return {
    detector: "cacheCreation-shift",
    signal: "cache-writes",
    severity: "alert",
    trigger: "version",
    agent: "claude",
    model: "claude-opus-5",
    servedModel: null,
    cliBefore: "2.1.271",
    cliAfter: "2.1.272",
    before: { value: 926, samples: 780, from: "2026-08-23", to: "2026-09-16" },
    after: { value: 3037, samples: 351, from: "2026-09-19", to: "2026-10-01" },
    ...over,
  };
}

function mismatch(over = {}) {
  return {
    detector: "model-mismatch",
    signal: "model-reroute",
    severity: "alert",
    trigger: "event",
    agent: "claude",
    model: "claude-opus-5",
    servedModel: "claude-sonnet-5",
    cliBefore: null,
    cliAfter: "2.1.272",
    before: null,
    after: { value: 0.09375, samples: 120, from: "2026-09-18", to: "2026-09-28" },
    ...over,
  };
}

function payload(findings = [cacheWrites()], over = {}) {
  return {
    schema: "nerf-watch-share/1",
    nerfWatchVersion: "0.2.0",
    window: { from: "2026-08-23", to: "2026-10-02" },
    agents: [{ id: "claude", sessions: 32, turns: 1280 }],
    findings,
    ...over,
  };
}

/** An issue body as the regression-report issue form writes it. */
function body(json) {
  const text = typeof json === "string" ? json : JSON.stringify(json, null, 2);
  return [
    "### Agent",
    "",
    "Claude Code",
    "",
    "### CLI version before the change",
    "",
    "2.1.271",
    "",
    "### Anonymized nerf-watch report (JSON)",
    "",
    "```json",
    text,
    "```",
    "",
    "### What you observed",
    "",
    "Rate limits ran out faster.",
  ].join("\n");
}

let nextNumber = 1;
function issue(json, over = {}) {
  return {
    number: nextNumber++,
    state: "open",
    labels: [{ name: "regression-report" }],
    user: { id: 1001, login: "someone" },
    created_at: "2026-10-03T10:00:00Z",
    body: body(json),
    ...over,
  };
}

const parse = (i) => parseIssue(i, { repoUrl: REPO_URL, now: NOW });

function rejects(json, re, over = {}) {
  const r = parse(issue(json, over));
  assert.equal(r.ok, false, `expected a rejection matching ${re}`);
  assert.match(r.reason, re);
  return r;
}

// ------------------------------------------------------------- accepted input

test("a well-formed report from the issue form is accepted", () => {
  const r = parse(issue(payload([cacheWrites(), mismatch()])));
  assert.equal(r.ok, true, r.reason);
  assert.equal(r.report.url, `${REPO_URL}/issues/${r.report.number}`);
  assert.equal(r.report.author, "id:1001");
  assert.equal(r.report.payload.findings.length, 2);
  assert.deepEqual(r.report.payload.findings[1].after, mismatch().after);
});

test("compact one-line JSON and tilde fences are accepted", () => {
  const i = issue(payload());
  i.body = `### Anonymized nerf-watch report (JSON)\n\n~~~\n${JSON.stringify(payload())}\n~~~\n`;
  assert.equal(parse(i).ok, true);
});

test("the extractor takes the first JSON block and ignores other code", () => {
  const b = "```sh\nnpx nerf-watch share\n```\n\n```json\n{\"a\":1}\n```\n";
  assert.equal(extractJsonBlock(b), '{"a":1}');
});

test("effect sizes per detector", () => {
  assert.equal(effectOf(cacheWrites()), 3037 / 926);
  assert.equal(effectOf(mismatch()), 0.09375);
  const hit = cacheWrites({ detector: "cacheHitRate-shift", signal: "cache-hit-rate", before: { value: 0.98, samples: 1, from: null, to: null }, after: { value: 0.8, samples: 1, from: null, to: null } });
  assert.ok(Math.abs(effectOf(hit) - -0.18) < 1e-9);
  const effort = cacheWrites({ detector: "effort-drop", signal: "effort-drop", before: { value: 4, samples: 8, from: null, to: null }, after: { value: 3, samples: 16, from: null, to: null } });
  assert.equal(effectOf(effort), -1);
  assert.equal(effectOf(cacheWrites({ before: { value: 0, samples: 1, from: null, to: null } })), null);
});

// ------------------------------------------------------------- aggregation

test("aggregates count distinct authors, take medians, and link every issue", () => {
  const a1 = issue(payload([cacheWrites({ after: { value: 1852, samples: 10, from: "2026-09-20", to: "2026-09-30" } })]), { user: { id: 1 }, created_at: "2026-10-01T00:00:00Z" });
  // Same author again, newer: replaces their earlier vote.
  const a1b = issue(payload([cacheWrites()]), { user: { id: 1 }, created_at: "2026-10-02T00:00:00Z" });
  const a2 = issue(payload([cacheWrites({ after: { value: 4630, samples: 10, from: "2026-09-17", to: "2026-10-02" } }), mismatch()]), { user: { id: 2 } });
  const bad = issue(payload([cacheWrites({ model: "<script>alert(1)</script>" })]), { user: { id: 3 } });
  const { aggregates, accepted, rejected } = processIssues([a1, a1b, a2, bad], { repoUrl: REPO_URL, now: NOW });
  assert.deepEqual(accepted, [a1.number, a1b.number, a2.number]);
  assert.deepEqual(rejected.map((r) => r.number), [bad.number]);
  assert.equal(aggregates.length, 2);
  const cw = aggregates.find((a) => a.signal === "cache-writes");
  assert.equal(cw.reports, 2);
  assert.equal(cw.alerts, 2);
  // a1b (3037/926 = 3.2797) and a2 (4630/926 = 5.0): median 4.1399
  assert.equal(cw.effect_median, Number((((3037 + 4630) / 926) / 2).toFixed(4)));
  assert.equal(cw.effect_unit, "ratio");
  assert.deepEqual(cw.cli_before, ["2.1.271"]);
  assert.equal(cw.first_seen, "2026-09-17");
  assert.equal(cw.last_seen, "2026-10-02");
  assert.deepEqual(
    cw.issues.map((x) => x.number),
    [a1.number, a1b.number, a2.number],
  );
  const mm = aggregates.find((a) => a.signal === "model-reroute");
  assert.equal(mm.reports, 1);
  assert.deepEqual(mm.served_models, ["claude-sonnet-5"]);
  assert.equal(mm.effect_unit, "share");
  assert.equal(aggregates[0], cw, "rows with more reports come first");
});

test("one issue votes once per row even if it repeats a finding", () => {
  const i = issue(payload([cacheWrites(), cacheWrites({ detector: "cacheCreation-drift", trigger: "time" })]));
  const rows = aggregate([parse(i).report]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].reports, 1);
});

test("no issues serializes to the committed empty file, so the first run commits nothing", () => {
  const committed = readFileSync(join(root, "data", "regressions.json"), "utf8");
  assert.equal(serialize(JSON.parse(committed), processIssues([], { repoUrl: REPO_URL }).aggregates), committed);
  assert.deepEqual(JSON.parse(committed), { reports: [], aggregates: [] });
});

test("aggregate output passes the site's data validator and renders escaped", () => {
  const dir = mkdtempSync(join(tmpdir(), "oal-agg-"));
  for (const d of ["scripts", "src", "data"]) cpSync(join(root, d), join(dir, d), { recursive: true });
  const issues = [issue(payload([cacheWrites(), mismatch()]), { user: { id: 7 } }), issue(payload([cacheWrites()]), { user: { id: 8 } })];
  writeFileSync(join(dir, "issues.json"), JSON.stringify(issues));
  const run = spawnSync(process.execPath, [join(dir, "scripts", "aggregate-regressions.mjs"), "--issues", join(dir, "issues.json")], {
    encoding: "utf8",
    env: { ...process.env, GITHUB_REPOSITORY: "Abelo9996/open-agent-lab" },
  });
  assert.equal(run.status, 0, run.stderr);
  assert.match(run.stdout, /accepted: 2; rejected: 0; aggregate rows: 2/);
  assert.match(run.stdout, /data\/regressions.json updated/);
  const again = spawnSync(process.execPath, [join(dir, "scripts", "aggregate-regressions.mjs"), "--issues", join(dir, "issues.json")], { encoding: "utf8" });
  assert.match(again.stdout, /unchanged/);
  assert.deepEqual(loadAll(dir).errors, []);
  const build = spawnSync(process.execPath, [join(dir, "scripts", "build.mjs")], { encoding: "utf8", cwd: dir });
  assert.equal(build.status, 0, build.stderr);
  const html = readFileSync(join(dir, "_site", "regressions", "index.html"), "utf8");
  assert.doesNotMatch(html, /No regression reports yet/);
  assert.match(html, /Cache writes jumped/);
  assert.match(html, /claude-opus-5 \(served: claude-sonnet-5\)/);
  assert.match(html, /<td class="num">2<\/td><td class="num mono"[^>]*>3\.28x<\/td>/);
  assert.match(html, /9\.4% of turns/);
  assert.match(html, new RegExp(`<a href="${REPO_URL}/issues/${issues[0].number}">#${issues[0].number}</a>`));
});

test("the site validator rejects a hand-edited aggregate with markup or a foreign link", () => {
  const dir = mkdtempSync(join(tmpdir(), "oal-agg-"));
  cpSync(join(root, "data"), join(dir, "data"), { recursive: true });
  const row = {
    agent: "claude",
    cli_version: "2.1.272",
    cli_before: [],
    model: "<img src=x onerror=alert(1)>",
    served_models: [],
    signal: "cache-writes",
    reports: 1,
    alerts: 1,
    effect_median: 3,
    effect_unit: "ratio",
    first_seen: "2026-09-19",
    last_seen: "2026-10-01",
    issues: [{ number: 1, url: "https://evil.example/issues/1" }],
  };
  writeFileSync(join(dir, "data", "regressions.json"), JSON.stringify({ reports: [], aggregates: [row] }));
  const { errors } = loadAll(dir);
  assert.ok(errors.some((e) => e.includes("aggregates[0].model")));
  assert.ok(errors.some((e) => e.includes("aggregates[0].issues[0].url")));
});

// ------------------------------------------------------------- hostile input

test("script tags and markup are rejected without echoing them", () => {
  for (const evil of ["<script>alert(1)</script>", "claude\"><img src=x onerror=alert(1)>", "javascript:alert(1)", "a&b"]) {
    const r = rejects(payload([cacheWrites({ model: evil })]), /findings\[0\]\.model/);
    assert.ok(!r.reason.includes(evil));
    assert.ok(!r.reason.includes("<"));
  }
  rejects(payload([cacheWrites({ cliAfter: "<svg/onload=alert(1)>" })]), /cliAfter/);
  rejects(payload([cacheWrites({ agent: "</td><script>" })]), /agent/);
});

test("path, email, URL and id leaks are rejected", () => {
  const cases = [
    ["/Users/alice/work/secret-repo", /path/],
    ["C:\\Users\\alice", /path/],
    ["~alice", /path/],
    ["claude-opus-5-..-alice", /path/],
    ["alice@example.org", /email/],
    ["https://proxy.internal", /path|URL/],
    ["3f2b9c1e-8d4a-4e6f-9b2a-1c3d5e7f9a0b", /session id/],
    ["arn-123456789012", /numeric id/],
    ["model-deadbeefdeadbeefdeadbeefdeadbeef", /hex id/],
    ["claude opus", /whitespace/],
  ];
  for (const [bad, re] of cases) rejects(payload([cacheWrites({ model: bad })]), re);
  rejects(payload([cacheWrites({ cliBefore: "/home/bob/.local/bin" })]), /path/);
  rejects(payload([cacheWrites()], { agents: [{ id: "alice@corp", sessions: 1, turns: 1 }] }), /email/);
  rejects(payload([cacheWrites()], { nerfWatchVersion: "/opt/nerf-watch" }), /path/);
});

test("huge payloads are rejected", () => {
  const big = payload([cacheWrites()], { agents: Array.from({ length: 2000 }, () => ({ id: "claude", sessions: 1, turns: 1 })) });
  assert.ok(JSON.stringify(big, null, 2).length > MAX_JSON_CHARS);
  rejects(big, /too large/);
  const i = issue(payload());
  i.body = "x".repeat(MAX_BODY_CHARS + 1);
  assert.match(parse(i).reason, /body: too large/);
  rejects(payload(Array.from({ length: 21 }, () => cacheWrites())), /findings/);
  rejects(payload([]), /findings/);
  rejects(payload([cacheWrites({ model: "m".repeat(81) })]), /length/);
  rejects(payload([cacheWrites()], { agents: Array.from({ length: 11 }, () => ({ id: "claude", sessions: 1, turns: 1 })) }), /agents/);
});

test("anything outside the schema is rejected", () => {
  rejects(payload([cacheWrites()], { extra: 1 }), /unexpected key/);
  rejects(payload([cacheWrites({ note: "hi" })]), /unexpected key/);
  rejects('{"__proto__": {"polluted": true}, "schema": "nerf-watch-share/1"}', /unexpected key|missing key/);
  assert.equal({}.polluted, undefined);
  rejects(payload([cacheWrites()], { schema: "nerf-watch-share/2" }), /schema/);
  rejects(payload([cacheWrites({ detector: "made-up" })]), /detector/);
  rejects(payload([cacheWrites({ signal: "tokens" })]), /signal: does not match/);
  rejects(payload([cacheWrites({ trigger: "time" })]), /trigger: does not match/);
  rejects(payload([cacheWrites({ severity: "info" })]), /severity/);
  rejects(payload([cacheWrites({ servedModel: "gpt-5" })]), /servedModel/);
  rejects(payload([mismatch({ servedModel: null })]), /servedModel/);
  rejects(payload([mismatch({ before: cacheWrites().before })]), /before: must be null/);
  rejects(payload([cacheWrites({ before: null })]), /before/);
  rejects(payload([mismatch({ after: { value: 3, samples: 1, from: null, to: null } })]), /out of range/);
  rejects(payload([cacheWrites({ after: { value: -1, samples: 1, from: null, to: null } })]), /out of range/);
  rejects(payload([cacheWrites({ after: { value: 1, samples: 1.5, from: null, to: null } })]), /integer/);
  rejects(body(payload()).replace("3037", "1e999").split("```json\n")[1].split("\n```")[0], /finite/);
  rejects(payload([cacheWrites({ after: { value: 1, samples: 1, from: "2026-02-30", to: null } })]), /calendar/);
  rejects(payload([cacheWrites({ after: { value: 1, samples: 1, from: "2027-01-01", to: null } })]), /out of range/);
  rejects(payload([cacheWrites({ after: { value: 1, samples: 1, from: "2026-10-01", to: "2026-09-01" } })]), /from is after to/);
  rejects(payload([cacheWrites({ model: 5 })]), /expected a string/);
  rejects("[1, 2, 3]", /no JSON block/);
  rejects("{not json", /not valid JSON/);
  const noBlock = issue(payload());
  noBlock.body = "### Anonymized nerf-watch report (JSON)\n\n_No response_\n";
  assert.match(parse(noBlock).reason, /no JSON block/);
});

test("only open, labeled issues that are not pull requests count", () => {
  rejects(payload(), /not open/, { state: "closed" });
  rejects(payload(), /label/, { labels: [{ name: "bug" }] });
  rejects(payload(), /pull request/, { pull_request: { url: "x" } });
  rejects(payload(), /author/, { user: null });
  assert.equal(parse(issue(payload(), { labels: ["regression-report"] })).ok, true);
});

test("a bad issue does not affect the others", () => {
  const good = issue(payload());
  const evil = issue(payload([cacheWrites({ model: "<script>" })]));
  const huge = issue(payload());
  huge.body = body("{" + '"a":1,'.repeat(5000) + '"b":1}');
  const { aggregates, rejected } = processIssues([evil, good, huge], { repoUrl: REPO_URL, now: NOW });
  assert.equal(aggregates.length, 1);
  assert.deepEqual(aggregates[0].issues, [{ number: good.number, url: `${REPO_URL}/issues/${good.number}` }]);
  assert.equal(rejected.length, 2);
});

test("validatePayload returns a copy built from validated fields only", () => {
  const p = payload([cacheWrites()]);
  const v = validatePayload(p, NOW);
  assert.notEqual(v, p);
  assert.notEqual(v.findings[0], p.findings[0]);
  assert.deepEqual(v.findings[0], p.findings[0]);
});
