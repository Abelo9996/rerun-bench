// Loads and validates everything under data/. No dependencies.
// Both the build and the CI validation step use this module, so a file that
// fails validation can never reach the site.

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, basename } from "node:path";
import { SIGNAL_EFFECT_UNIT } from "./regressions.mjs";

export const RESULT_NAME = /^(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.json$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;
const HTTPS = /^https:\/\/\S+$/;

export const REGRESSION_SIGNALS = [
  "model-reroute",
  "effort-drop",
  "context-shrink",
  "cache-writes",
  "cache-hit-rate",
  "tool-errors",
  "tokens",
  "cost",
  "pass-rate",
  "other",
];
export const REGRESSION_STATUSES = ["open", "confirmed", "not-reproduced", "explained"];
export const LAUNCH_STATUSES = ["planned", "running", "published"];

class Checker {
  constructor(file) {
    this.file = file;
    this.errors = [];
  }
  fail(path, msg) {
    this.errors.push(`${this.file}: ${path}: ${msg}`);
  }
  isObj(v, path) {
    if (v === null || typeof v !== "object" || Array.isArray(v)) {
      this.fail(path, "expected an object");
      return false;
    }
    return true;
  }
  isArr(v, path, { nonEmpty = false } = {}) {
    if (!Array.isArray(v)) {
      this.fail(path, "expected an array");
      return false;
    }
    if (nonEmpty && v.length === 0) {
      this.fail(path, "must not be empty");
      return false;
    }
    return true;
  }
  str(v, path, { nullable = false, pattern = null, oneOf = null } = {}) {
    if (v === null && nullable) return true;
    if (typeof v !== "string" || v.length === 0) {
      this.fail(path, `expected a non-empty string${nullable ? " or null" : ""}`);
      return false;
    }
    if (pattern && !pattern.test(v)) {
      this.fail(path, `"${v}" does not match ${pattern}`);
      return false;
    }
    if (oneOf && !oneOf.includes(v)) {
      this.fail(path, `"${v}" is not one of ${oneOf.join(", ")}`);
      return false;
    }
    return true;
  }
  num(v, path, { nullable = false, min = -Infinity, max = Infinity, int = false } = {}) {
    if (v === null && nullable) return true;
    if (typeof v !== "number" || !Number.isFinite(v)) {
      this.fail(path, `expected a number${nullable ? " or null" : ""}`);
      return false;
    }
    if (int && !Number.isInteger(v)) {
      this.fail(path, "expected an integer");
      return false;
    }
    if (v < min || v > max) {
      this.fail(path, `${v} is outside [${min}, ${max}]`);
      return false;
    }
    return true;
  }
  bool(v, path) {
    if (typeof v !== "boolean") {
      this.fail(path, "expected true or false");
      return false;
    }
    return true;
  }
  interval(v, path) {
    if (!this.isArr(v, path)) return false;
    if (v.length !== 2) {
      this.fail(path, "expected [low, high]");
      return false;
    }
    const ok = this.num(v[0], `${path}[0]`, { min: 0, max: 1 }) && this.num(v[1], `${path}[1]`, { min: 0, max: 1 });
    if (ok && v[0] > v[1] + 1e-9) {
      this.fail(path, "low is greater than high");
      return false;
    }
    return ok;
  }
}

const near = (a, b) => Math.abs(a - b) < 1e-6;

function readJson(path, ck) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (e) {
    ck.fail("(file)", `not valid JSON: ${e.message}`);
    return undefined;
  }
}

function validateStat(ck, v, path) {
  // rerun-bench per-task summary for cost, tokens and wall time.
  if (!ck.isObj(v, path)) return;
  ck.num(v.n, `${path}.n`, { min: 0, int: true });
  for (const key of ["mean", "median", "min", "max"]) {
    if (key in v) ck.num(v[key], `${path}.${key}`, { nullable: true });
  }
}

export function validateResult(path) {
  const name = basename(path);
  const ck = new Checker(`data/results/${name}`);
  const m = RESULT_NAME.exec(name);
  if (!m) ck.fail("(file name)", "must be <YYYY-MM-DD>-<label>.json with a lowercase label of letters, digits and hyphens");
  const doc = readJson(path, ck);
  if (doc === undefined || !ck.isObj(doc, "(root)")) return { errors: ck.errors };

  ck.str(doc.generated_at, "generated_at", { pattern: DATETIME });
  ck.str(doc.rerun_bench_version, "rerun_bench_version");
  if (ck.isArr(doc.entries, "entries", { nonEmpty: true })) {
    const runIds = new Set();
    doc.entries.forEach((e, i) => {
      const p = `entries[${i}]`;
      if (!ck.isObj(e, p)) return;
      ck.str(e.run_id, `${p}.run_id`);
      if (runIds.has(e.run_id)) ck.fail(`${p}.run_id`, `duplicate run_id "${e.run_id}"`);
      runIds.add(e.run_id);
      ck.str(e.agent, `${p}.agent`);
      ck.str(e.model, `${p}.model`, { nullable: true });
      ck.str(e.cli_version, `${p}.cli_version`, { nullable: true });
      ck.str(e.started_at, `${p}.started_at`, { pattern: DATETIME });
      const mt = e.metrics;
      if (!ck.isObj(mt, `${p}.metrics`)) return;
      const q = `${p}.metrics`;
      ck.num(mt.n_tasks, `${q}.n_tasks`, { min: 1, int: true });
      ck.num(mt.n_runs, `${q}.n_runs`, { min: 1, int: true });
      ck.num(mt.min_runs_per_task, `${q}.min_runs_per_task`, { min: 1, int: true });
      ck.num(mt.passes, `${q}.passes`, { min: 0, max: mt.n_runs ?? Infinity, int: true });
      ck.num(mt.k, `${q}.k`, { min: 1, int: true });
      for (const key of ["pass_rate", "macro_pass_rate", "pass_at_k", "pass_hat_k", "flip_rate", "flaky_task_fraction"]) {
        ck.num(mt[key], `${q}.${key}`, { min: 0, max: 1 });
      }
      ck.interval(mt.pass_rate_ci95, `${q}.pass_rate_ci95`);
      // The task-level bootstrap resamples tasks, so it is null for a single-task
      // report (rerun-bench emits null when n_tasks < 2). Accept null there; still
      // require an interval once there are at least two tasks to resample.
      const macroCi = mt.macro_pass_rate_task_bootstrap_ci95;
      if (macroCi === null) {
        if (mt.n_tasks >= 2) {
          ck.fail(`${q}.macro_pass_rate_task_bootstrap_ci95`, "is null, but a task-bootstrap interval is expected once there are at least 2 tasks");
        }
      } else if (macroCi !== undefined) {
        ck.interval(macroCi, `${q}.macro_pass_rate_task_bootstrap_ci95`);
      }
      for (const key of [
        "total_cost_usd",
        "mean_cost_usd",
        "median_cost_usd",
        "cost_per_success_usd",
        "tokens_mean",
        "tokens_median",
        "output_tokens_median",
        "tokens_cv_within_task",
        "wall_time_mean_s",
        "wall_time_median_s",
        "wall_time_total_s",
        "approach_similarity",
      ]) {
        if (key in mt) ck.num(mt[key], `${q}.${key}`, { nullable: true, min: 0 });
      }
      if (typeof mt.passes === "number" && typeof mt.n_runs === "number" && typeof mt.pass_rate === "number") {
        if (!near(mt.pass_rate, mt.passes / mt.n_runs)) ck.fail(`${q}.pass_rate`, "does not equal passes / n_runs");
        const ci = mt.pass_rate_ci95;
        if (Array.isArray(ci) && (mt.pass_rate < ci[0] - 1e-9 || mt.pass_rate > ci[1] + 1e-9)) {
          ck.fail(`${q}.pass_rate_ci95`, "does not contain pass_rate");
        }
      }
      if (typeof mt.pass_hat_k === "number" && typeof mt.pass_at_k === "number" && mt.pass_hat_k > mt.pass_at_k + 1e-9) {
        ck.fail(`${q}.pass_hat_k`, "is greater than pass_at_k, which cannot happen");
      }
      if (!ck.isObj(mt.per_task, `${q}.per_task`)) return;
      const tasks = Object.entries(mt.per_task);
      if (tasks.length !== mt.n_tasks) ck.fail(`${q}.per_task`, `has ${tasks.length} tasks but n_tasks is ${mt.n_tasks}`);
      let runs = 0;
      let passes = 0;
      for (const [tid, t] of tasks) {
        const tp = `${q}.per_task.${tid}`;
        if (!ck.isObj(t, tp)) continue;
        ck.num(t.n, `${tp}.n`, { min: 1, int: true });
        ck.num(t.passes, `${tp}.passes`, { min: 0, max: t.n ?? Infinity, int: true });
        ck.num(t.pass_rate, `${tp}.pass_rate`, { min: 0, max: 1 });
        ck.num(t.flip_rate, `${tp}.flip_rate`, { min: 0, max: 1 });
        if (ck.isArr(t.outcomes, `${tp}.outcomes`)) {
          if (!t.outcomes.every((o) => typeof o === "boolean")) ck.fail(`${tp}.outcomes`, "must contain only true or false");
          if (t.outcomes.length !== t.n) ck.fail(`${tp}.outcomes`, `has ${t.outcomes.length} entries but n is ${t.n}`);
          if (t.outcomes.filter(Boolean).length !== t.passes) ck.fail(`${tp}.outcomes`, "number of true entries does not equal passes");
        }
        for (const key of ["cost_usd", "total_tokens", "output_tokens", "wall_time_s"]) {
          if (key in t) validateStat(ck, t[key], `${tp}.${key}`);
        }
        runs += t.n || 0;
        passes += t.passes || 0;
      }
      if (runs !== mt.n_runs) ck.fail(`${q}.per_task`, `runs sum to ${runs} but n_runs is ${mt.n_runs}`);
      if (passes !== mt.passes) ck.fail(`${q}.per_task`, `passes sum to ${passes} but passes is ${mt.passes}`);
    });
  }

  // Optional lab metadata added by whoever submits the file.
  if (doc.lab !== undefined && ck.isObj(doc.lab, "lab")) {
    const lab = doc.lab;
    if (lab.title !== undefined) ck.str(lab.title, "lab.title");
    if (lab.pilot !== undefined) ck.bool(lab.pilot, "lab.pilot");
    if (lab.date !== undefined && ck.str(lab.date, "lab.date", { pattern: DATE }) && m && lab.date !== m[1]) {
      ck.fail("lab.date", `"${lab.date}" does not match the date in the file name (${m[1]})`);
    }
    if (lab.source_url !== undefined) ck.str(lab.source_url, "lab.source_url", { pattern: HTTPS });
    if (lab.harness_commit !== undefined) ck.str(lab.harness_commit, "lab.harness_commit", { pattern: /^[0-9a-f]{7,40}$/ });
    if (lab.machine !== undefined) ck.str(lab.machine, "lab.machine");
    if (lab.launch !== undefined) ck.str(lab.launch, "lab.launch");
    if (lab.notes !== undefined && ck.isArr(lab.notes, "lab.notes")) {
      lab.notes.forEach((n, i) => ck.str(n, `lab.notes[${i}]`));
    }
  }
  return {
    errors: ck.errors,
    result: ck.errors.length ? null : { file: name, date: m[1], label: m[2], ...doc, lab: doc.lab || {} },
  };
}

function validateAgents(path) {
  const ck = new Checker("data/agents.json");
  const doc = readJson(path, ck);
  if (doc === undefined || !ck.isObj(doc, "(root)")) return { errors: ck.errors };
  const ids = new Set();
  if (ck.isArr(doc.agents, "agents", { nonEmpty: true })) {
    doc.agents.forEach((a, i) => {
      const p = `agents[${i}]`;
      if (!ck.isObj(a, p)) return;
      ck.str(a.id, `${p}.id`, { pattern: /^[a-z0-9-]+$/ });
      if (ids.has(a.id)) ck.fail(`${p}.id`, `duplicate id "${a.id}"`);
      ids.add(a.id);
      ck.str(a.name, `${p}.name`);
      ck.str(a.homepage, `${p}.homepage`, { nullable: true, pattern: HTTPS });
    });
  }
  return { errors: ck.errors, agents: doc.agents };
}

function validateTasks(path) {
  const ck = new Checker("data/tasks.json");
  const doc = readJson(path, ck);
  if (doc === undefined || !ck.isObj(doc, "(root)")) return { errors: ck.errors };
  ck.str(doc.suite, "suite");
  ck.str(doc.source_url, "source_url", { pattern: HTTPS });
  if (ck.isArr(doc.tasks, "tasks", { nonEmpty: true })) {
    doc.tasks.forEach((t, i) => {
      const p = `tasks[${i}]`;
      if (!ck.isObj(t, p)) return;
      ck.str(t.id, `${p}.id`, { pattern: /^[a-z0-9-]+$/ });
      ck.str(t.title, `${p}.title`);
      if (ck.isArr(t.tags, `${p}.tags`)) t.tags.forEach((g, j) => ck.str(g, `${p}.tags[${j}]`));
      ck.num(t.timeout_s, `${p}.timeout_s`, { nullable: true, min: 1, int: true });
    });
  }
  return { errors: ck.errors, tasks: doc };
}

function validateRegressions(path, agentIds) {
  const ck = new Checker("data/regressions.json");
  const doc = readJson(path, ck);
  if (doc === undefined || !ck.isObj(doc, "(root)")) return { errors: ck.errors };
  if (ck.isArr(doc.reports, "reports")) {
    const ids = new Set();
    doc.reports.forEach((r, i) => {
      const p = `reports[${i}]`;
      if (!ck.isObj(r, p)) return;
      ck.str(r.id, `${p}.id`, { pattern: /^[a-z0-9-]+$/ });
      if (ids.has(r.id)) ck.fail(`${p}.id`, `duplicate id "${r.id}"`);
      ids.add(r.id);
      ck.str(r.reported_at, `${p}.reported_at`, { pattern: DATE });
      if (ck.str(r.agent, `${p}.agent`) && agentIds && !agentIds.has(r.agent)) {
        ck.fail(`${p}.agent`, `"${r.agent}" is not in data/agents.json`);
      }
      ck.str(r.model, `${p}.model`, { nullable: true });
      ck.str(r.cli_before, `${p}.cli_before`, { nullable: true });
      ck.str(r.cli_after, `${p}.cli_after`, { nullable: true });
      ck.str(r.signal, `${p}.signal`, { oneOf: REGRESSION_SIGNALS });
      ck.str(r.summary, `${p}.summary`);
      ck.num(r.independent_reports, `${p}.independent_reports`, { min: 1, int: true });
      ck.str(r.status, `${p}.status`, { oneOf: REGRESSION_STATUSES });
      ck.str(r.issue_url, `${p}.issue_url`, { pattern: HTTPS });
    });
  }
  // Written by scripts/aggregate-regressions.mjs from open regression-report issues.
  const aggregates = doc.aggregates === undefined ? [] : doc.aggregates;
  if (ck.isArr(aggregates, "aggregates")) {
    const SAFE = /^[A-Za-z0-9][A-Za-z0-9_.+\-\[\]]{0,79}$/;
    const ISSUE = /^https:\/\/github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9._-]+\/issues\/[1-9]\d*$/;
    const keys = new Set();
    aggregates.forEach((a, i) => {
      const p = `aggregates[${i}]`;
      if (!ck.isObj(a, p)) return;
      ck.str(a.agent, `${p}.agent`, { pattern: /^[a-z][a-z0-9-]{0,31}$/ });
      ck.str(a.cli_version, `${p}.cli_version`, { pattern: SAFE });
      ck.str(a.model, `${p}.model`, { pattern: SAFE });
      ck.str(a.signal, `${p}.signal`, { oneOf: Object.keys(SIGNAL_EFFECT_UNIT) });
      const key = `${a.agent}|${a.cli_version}|${a.model}|${a.signal}`;
      if (keys.has(key)) ck.fail(p, "duplicate agent, CLI version, model and signal");
      keys.add(key);
      for (const f of ["cli_before", "served_models"]) {
        if (ck.isArr(a[f], `${p}.${f}`)) a[f].forEach((v, j) => ck.str(v, `${p}.${f}[${j}]`, { pattern: SAFE }));
      }
      ck.num(a.reports, `${p}.reports`, { min: 1, int: true });
      ck.num(a.alerts, `${p}.alerts`, { min: 0, max: a.reports ?? Infinity, int: true });
      ck.num(a.effect_median, `${p}.effect_median`, { nullable: true, min: -1e9, max: 1e9 });
      if (a.effect_unit !== (SIGNAL_EFFECT_UNIT[a.signal] ?? null)) ck.fail(`${p}.effect_unit`, "does not match the signal");
      ck.str(a.first_seen, `${p}.first_seen`, { nullable: true, pattern: DATE });
      ck.str(a.last_seen, `${p}.last_seen`, { nullable: true, pattern: DATE });
      if (ck.isArr(a.issues, `${p}.issues`, { nonEmpty: true })) {
        a.issues.forEach((x, j) => {
          if (!ck.isObj(x, `${p}.issues[${j}]`)) return;
          ck.num(x.number, `${p}.issues[${j}].number`, { min: 1, int: true });
          if (ck.str(x.url, `${p}.issues[${j}].url`, { pattern: ISSUE }) && !x.url.endsWith(`/issues/${x.number}`)) {
            ck.fail(`${p}.issues[${j}].url`, "does not match the issue number");
          }
        });
      }
    });
  }
  return { errors: ck.errors, reports: doc.reports || [], aggregates: Array.isArray(aggregates) ? aggregates : [] };
}

function validateLaunches(path, resultFiles) {
  const ck = new Checker("data/launches.json");
  const doc = readJson(path, ck);
  if (doc === undefined || !ck.isObj(doc, "(root)")) return { errors: ck.errors };
  if (ck.isArr(doc.launches, "launches")) {
    doc.launches.forEach((l, i) => {
      const p = `launches[${i}]`;
      if (!ck.isObj(l, p)) return;
      ck.str(l.model, `${p}.model`);
      ck.str(l.vendor, `${p}.vendor`);
      ck.str(l.announced_at, `${p}.announced_at`, { pattern: DATETIME });
      ck.str(l.status, `${p}.status`, { oneOf: LAUNCH_STATUSES });
      ck.str(l.published_at, `${p}.published_at`, { nullable: true, pattern: DATETIME });
      if (ck.str(l.results_file, `${p}.results_file`, { nullable: true }) && l.results_file && !resultFiles.has(l.results_file)) {
        ck.fail(`${p}.results_file`, `"${l.results_file}" is not a file in data/results/`);
      }
      if (l.status === "published" && (!l.results_file || !l.published_at)) {
        ck.fail(p, "a published launch needs results_file and published_at");
      }
    });
  }
  return { errors: ck.errors, launches: doc.launches || [] };
}

// Loads everything. Returns { errors, warnings, data }.
export function loadAll(root) {
  const dataDir = join(root, "data");
  const errors = [];
  const warnings = [];
  const need = (f) => {
    const p = join(dataDir, f);
    if (!existsSync(p)) errors.push(`data/${f}: missing`);
    return p;
  };

  const ag = validateAgents(need("agents.json"));
  errors.push(...ag.errors);
  const agentIds = new Set((ag.agents || []).map((a) => a.id));

  const tk = validateTasks(need("tasks.json"));
  errors.push(...tk.errors);

  const resultsDir = join(dataDir, "results");
  const files = existsSync(resultsDir) ? readdirSync(resultsDir).filter((f) => !f.startsWith(".")).sort() : [];
  const results = [];
  for (const f of files) {
    if (!f.endsWith(".json")) {
      errors.push(`data/results/${f}: only .json files belong in data/results/`);
      continue;
    }
    const r = validateResult(join(resultsDir, f));
    errors.push(...r.errors);
    if (r.result) {
      for (const e of r.result.entries) {
        if (!agentIds.has(e.agent)) warnings.push(`data/results/${f}: agent "${e.agent}" is not in data/agents.json; its id is shown as the name`);
      }
      results.push(r.result);
    }
  }
  // Newest first; ties broken by label.
  results.sort((a, b) => (a.date === b.date ? a.label.localeCompare(b.label) : b.date.localeCompare(a.date)));

  const rg = validateRegressions(need("regressions.json"), agentIds);
  errors.push(...rg.errors);
  const ln = validateLaunches(need("launches.json"), new Set(files));
  errors.push(...ln.errors);

  return {
    errors,
    warnings,
    data: {
      agents: ag.agents || [],
      tasks: tk.tasks || { tasks: [] },
      results,
      regressions: rg.reports || [],
      regressionAggregates: rg.aggregates || [],
      launches: ln.launches || [],
    },
  };
}
