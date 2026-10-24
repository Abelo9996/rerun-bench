// Checks that the validator accepts the committed data and rejects broken
// result files. Run with `npm test`.

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, cpSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { loadAll, validateResult } from "../scripts/lib/data.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const pilot = join(root, "data", "results", "2026-10-03-pilot.json");

function withResult(mutate, name = "2026-10-03-test.json") {
  const dir = mkdtempSync(join(tmpdir(), "oal-"));
  const doc = JSON.parse(readFileSync(pilot, "utf8"));
  mutate(doc);
  const p = join(dir, name);
  writeFileSync(p, JSON.stringify(doc));
  return validateResult(p);
}

test("committed data validates", () => {
  const { errors } = loadAll(root);
  assert.deepEqual(errors, []);
});

test("an unmodified rerun-bench report without lab metadata validates", () => {
  const r = withResult((d) => delete d.lab, "2026-10-03-plain.json");
  assert.deepEqual(r.errors, []);
  assert.equal(r.result.label, "plain");
});

test("bad file name is rejected", () => {
  const r = withResult(() => {}, "pilot.json");
  assert.ok(r.errors.some((e) => e.includes("file name")));
});

test("pass rate outside its interval is rejected", () => {
  const r = withResult((d) => {
    d.entries[0].metrics.pass_rate_ci95 = [0.1, 0.2];
  });
  assert.ok(r.errors.some((e) => e.includes("does not contain pass_rate")));
});

test("outcomes that disagree with passes are rejected", () => {
  const r = withResult((d) => {
    d.entries[1].metrics.per_task["edit-config"].outcomes = [true, false, true];
  });
  assert.ok(r.errors.some((e) => e.includes("number of true entries")));
});

test("lab.date must match the file name", () => {
  const r = withResult((d) => {
    d.lab.date = "2026-10-04";
  });
  assert.ok(r.errors.some((e) => e.includes("lab.date")));
});

// A single-task report cannot bootstrap a task-level interval, so rerun-bench
// emits macro_pass_rate_task_bootstrap_ci95: null for it. The validator must
// accept that null rather than demanding an array.
function singleTask(macroCi) {
  const dir = mkdtempSync(join(tmpdir(), "oal-"));
  const doc = {
    generated_at: "2026-10-03T08:00:00+00:00",
    rerun_bench_version: "0.3.0",
    entries: [
      {
        run_id: "claude",
        agent: "claude",
        model: "claude-opus-5-5",
        cli_version: "2.1.0 (Claude Code)",
        started_at: "2026-10-03T08:00:00+00:00",
        metrics: {
          n_tasks: 1,
          n_runs: 2,
          min_runs_per_task: 2,
          passes: 2,
          k: 2,
          pass_rate: 1,
          macro_pass_rate: 1,
          pass_at_k: 1,
          pass_hat_k: 1,
          flip_rate: 0,
          flaky_task_fraction: 0,
          pass_rate_ci95: [0.3, 1],
          macro_pass_rate_task_bootstrap_ci95: macroCi,
          per_task: { "only-task": { n: 2, passes: 2, pass_rate: 1, flip_rate: 0, outcomes: [true, true] } },
        },
      },
    ],
  };
  const p = join(dir, "2026-10-03-single.json");
  writeFileSync(p, JSON.stringify(doc));
  return validateResult(p);
}

test("a single-task report with a null task-bootstrap interval validates", () => {
  const r = singleTask(null);
  assert.deepEqual(r.errors, []);
});

test("a null task-bootstrap interval with two or more tasks is rejected", () => {
  const r = withResult((d) => {
    d.entries[0].metrics.macro_pass_rate_task_bootstrap_ci95 = null;
  });
  assert.ok(r.errors.some((e) => e.includes("at least 2 tasks")));
});

test("regression reports with unknown agents are rejected", () => {
  const dir = mkdtempSync(join(tmpdir(), "oal-"));
  cpSync(join(root, "data"), join(dir, "data"), { recursive: true });
  writeFileSync(
    join(dir, "data", "regressions.json"),
    JSON.stringify({
      reports: [
        {
          id: "x-1",
          reported_at: "2026-10-03",
          agent: "nope",
          model: null,
          cli_before: null,
          cli_after: null,
          signal: "tokens",
          summary: "s",
          independent_reports: 1,
          status: "open",
          issue_url: "https://example.org/1",
        },
      ],
    }),
  );
  const { errors } = loadAll(dir);
  assert.ok(errors.some((e) => e.includes('"nope" is not in data/agents.json')));
});
