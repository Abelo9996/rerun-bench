#!/usr/bin/env node
// Builds the static site from data/*.json into _site/.
// Usage: node scripts/build.mjs [--out _site]
// Fails (exit 1) if any data file does not validate.

import { mkdirSync, writeFileSync, copyFileSync, rmSync, readdirSync, existsSync } from "node:fs";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { loadAll } from "./lib/data.mjs";
import {
  esc,
  pct,
  ci,
  ciWords,
  int,
  usd,
  secs,
  dec,
  compact,
  intervalChart,
  multiDotChart,
  rangeChart,
  consistencyGrid,
} from "./lib/charts.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outArg = process.argv.indexOf("--out");
const OUT = join(root, outArg > -1 ? process.argv[outArg + 1] : "_site");
// Absolute base path, only used by 404.html (served at arbitrary depths).
const BASE = process.env.SITE_BASE || "/rerun-bench/";
// Absolute site URL, used for canonical links and social preview meta tags.
const SITE_URL = process.env.SITE_URL || "https://abelo9996.github.io/rerun-bench/";
const SOCIAL_IMAGE = `${SITE_URL}assets/social-preview.png`;

// The site and its data live under site/ in the rerun-bench repository.
const REPO = "https://github.com/Abelo9996/rerun-bench";
const SITE_TREE = `${REPO}/tree/main/site`;
const SITE_BLOB = `${REPO}/blob/main/site`;
const GH = "https://github.com/Abelo9996";
const TOOLS = {
  rerunBench: `${GH}/rerun-bench`,
  metrics: `${GH}/rerun-bench/blob/main/docs/METRICS.md`,
  nerfWatch: `${GH}/nerf-watch`,
  snapBack: `${GH}/snap-back`,
  agentFence: `${GH}/agent-fence`,
  launchDayKit: `${GH}/launch-day-kit`,
};
// The regression watch and nerf-watch issue intake stay in the open-agent-lab
// repository, because published nerf-watch versions open issues there.
const REGRESSION_REPO = "https://github.com/Abelo9996/open-agent-lab";
const ISSUE_FORM = `${REGRESSION_REPO}/issues/new?template=regression-report.yml`;

const { errors, warnings, data } = loadAll(root);
for (const w of warnings) console.warn(`warning: ${w}`);
if (errors.length) {
  for (const e of errors) console.error(`error: ${e}`);
  process.exit(1);
}

let commit = process.env.GITHUB_SHA || "";
if (!commit) {
  try {
    commit = execSync("git rev-parse HEAD", { cwd: root, stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    commit = "";
  }
}
const shortCommit = commit.slice(0, 7);

const agentName = (id) => data.agents.find((a) => a.id === id)?.name || id;
const taskById = Object.fromEntries(data.tasks.tasks.map((t) => [t.id, t]));
const byName = (a, b) => agentName(a.agent).localeCompare(agentName(b.agent)) || a.run_id.localeCompare(b.run_id);

// ---------------------------------------------------------------- layout

const NAV = [
  ["", "Home"],
  ["results/", "Results"],
  ["methodology/", "Methodology"],
  ["regressions/", "Regression watch"],
  ["launches/", "Launch day"],
];

const mark = `<svg class="logo" width="28" height="20" viewBox="0 0 28 20" aria-hidden="true" focusable="false"><rect x="1" y="6" width="4" height="13" rx="1"/><rect x="8" y="2" width="4" height="17" rx="1"/><rect x="15" y="8" width="4" height="11" rx="1"/><rect x="22" y="2" width="4" height="17" rx="1" class="logo-hi"/></svg>`;

// Runs before first paint: applies a stored theme choice and marks that
// scripts are available, so script-only controls never show without them.
const HEAD_SCRIPT = `(function(){var d=document.documentElement;d.classList.add("js");try{var t=localStorage.getItem("oal-theme");if(t==="light"||t==="dark")d.setAttribute("data-theme",t)}catch(e){}})();`;

const themeIcon = `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 1.75a6.25 6.25 0 0 1 0 12.5z" fill="currentColor"/></svg>`;

const DEFAULT_IMAGE = {
  url: SOCIAL_IMAGE,
  w: 1280,
  h: 640,
  alt: "open agent lab: coding agents, measured more than once. A pass and fail grid of repeated runs per task.",
};

function layout({ path, title, description, body, absolute = false, image = DEFAULT_IMAGE, ogType = "website", head = "", fullTitle: titleOverride }) {
  const depth = path === "" ? 0 : path.split("/").filter(Boolean).length;
  const pre = absolute ? BASE : depth ? "../".repeat(depth) : "./";
  const nav = NAV.map(([href, label]) => {
    const cur = href === path ? ' aria-current="page"' : "";
    return `<li><a href="${pre}${href}"${cur}>${esc(label)}</a></li>`;
  }).join("");
  const fullTitle = titleOverride || (path === "" ? "open agent lab" : `${title} | open agent lab`);
  const url = absolute ? SITE_URL : `${SITE_URL}${path}`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>${esc(fullTitle)}</title>
<meta name="description" content="${esc(description)}">
${absolute ? "" : `<link rel="canonical" href="${esc(url)}">\n`}<meta property="og:type" content="${esc(ogType)}">
<meta property="og:site_name" content="open agent lab">
<meta property="og:title" content="${esc(fullTitle)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:url" content="${esc(url)}">
<meta property="og:image" content="${esc(image.url)}">
<meta property="og:image:width" content="${image.w}">
<meta property="og:image:height" content="${image.h}">
<meta property="og:image:alt" content="${esc(image.alt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${esc(fullTitle)}">
<meta name="twitter:description" content="${esc(description)}">
<meta name="twitter:image" content="${esc(image.url)}">
<meta name="twitter:image:alt" content="${esc(image.alt)}">
${head}
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#fcfdfc">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#151b1a">
<link rel="icon" href="${pre}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="${pre}assets/style.css">
<script>${HEAD_SCRIPT}</script>
<script src="${pre}assets/site.js" defer></script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header" id="top">
  <div class="wrap header-inner">
    <a class="brand" href="${pre}">${mark}<span>open agent lab</span></a>
    <nav aria-label="Main"><ul>${nav}</ul></nav>
    <button class="theme-toggle" type="button" data-theme-toggle aria-label="Color theme: follows system">${themeIcon}<span class="theme-label">auto</span></button>
  </div>
  <div class="ruler" aria-hidden="true"></div>
</header>
<main id="main" class="wrap">
${body}
</main>
<footer class="site-footer">
  <div class="wrap footer-inner">
    <p>Code under the MIT license. Data under CC BY 4.0. Every number on this site comes from a file in <a href="${SITE_TREE}/data">data/</a>.</p>
    <p class="mono">${shortCommit ? `built from <a href="${REPO}/commit/${esc(commit)}">${esc(shortCommit)}</a>` : "local build"} &middot; <a href="${REPO}">source</a> &middot; <a href="${REPO}/issues">issues</a></p>
  </div>
</footer>
<div class="tip" role="tooltip" id="tip" hidden></div>
<p class="sr-only" aria-live="polite" id="live"></p>
</body>
</html>
`;
}

const badge = (text, kind = "") => `<span class="badge ${kind}">${esc(text)}</span>`;
const sectionHead = (num, label, title, id) =>
  `<p class="eyebrow"><span class="mono">${num}</span> ${esc(label)}</p><h2${id ? ` id="${id}"` : ""}>${title}</h2>`;

function resultBadges(r) {
  const n = Math.min(...r.entries.map((e) => e.metrics.min_runs_per_task));
  const b = [];
  if (r.lab.pilot) b.push(badge(`Pilot, n=${n} per task`, "pilot"));
  else b.push(badge(`n=${n} per task`));
  if (r.lab.launch) b.push(badge(`Launch day: ${r.lab.launch}`));
  return b.join(" ");
}

function overlapVerdict(entries) {
  if (entries.length < 2) return "One agent in this result set, so there is no comparison to make.";
  const apart = [];
  for (let i = 0; i < entries.length; i++) {
    for (let j = i + 1; j < entries.length; j++) {
      const a = entries[i].metrics.pass_rate_ci95;
      const b = entries[j].metrics.pass_rate_ci95;
      if (a[1] < b[0] || b[1] < a[0]) apart.push(`${agentName(entries[i].agent)} and ${agentName(entries[j].agent)}`);
    }
  }
  if (!apart.length) {
    return "The 95% intervals overlap for every pair of agents here, so this data does not show that any agent has a higher pass rate than another.";
  }
  return `The 95% intervals do not overlap for: ${apart.join("; ")}. The intervals treat runs as independent, so they understate uncertainty about the task population; see the task-bootstrap interval in the table below before reading this as a difference.`;
}

// One or two sentences a stranger can read without knowing the metrics:
// what each agent scored, on how many runs, and whether this is a pilot.
function plainSummary(r, name = agentName) {
  const es = r.entries.slice().sort((a, b) => name(a.agent).localeCompare(name(b.agent)));
  const nTasks = Math.max(...es.map((e) => e.metrics.n_tasks));
  const runs = Math.min(...es.map((e) => e.metrics.min_runs_per_task));
  const parts = es.map((e) => `${name(e.agent)} passed ${e.metrics.passes} of ${e.metrics.n_runs} runs`);
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0];
  let out = `${list}: ${nTasks} tasks, each run ${runs} times, every run scored only by the task's own test script.`;
  if (r.lab.pilot) out += " This is a pilot: it checks that the harness works end to end against real CLIs, and it is too small to rank agents.";
  return out;
}

// Plain-language meaning of the headline numbers, shown next to them.
function metricKey(k) {
  const rows = [
    ["pass rate [low, high]", "Share of runs that passed. The brackets are the 95% interval: the range of true pass rates these runs are consistent with. Few runs give a wide range."],
    [`pass^${k}`, `Chance that all ${k} runs of a task pass. Read it as how far you can trust a single run.`],
    ["flip rate", "Chance that two runs of the same task disagree, one pass and one fail. 0% means every task gave the same result every time."],
    ["median tokens", "Tokens a typical run used, including cached input."],
  ];
  return `<dl class="key">${rows.map(([t, d]) => `<div><dt>${esc(t)}</dt><dd>${esc(d)}</dd></div>`).join("")}</dl>`;
}

const entryLabel = (e) => agentName(e.agent);
const entrySub = (e) => [e.model, e.cli_version].filter(Boolean).join(" · ");

// ---------------------------------------------------------------- results

function setupTable(r) {
  const rows = r.entries
    .slice()
    .sort(byName)
    .map(
      (e) => `<tr><th scope="row">${esc(agentName(e.agent))}</th><td class="mono">${esc(e.cli_version || "not reported")}</td><td class="mono">${esc(
        e.model || "default (not reported)",
      )}</td><td class="num">${e.metrics.n_tasks}</td><td class="num">${e.metrics.min_runs_per_task}</td><td class="num">${e.metrics.n_runs}</td><td class="mono">${esc(
        e.started_at.replace("T", " ").replace(/\+00:00$|Z$/, " UTC"),
      )}</td></tr>`,
    )
    .join("");
  return `<div class="tablewrap"><table class="data">
<caption class="sr-only">Run setup</caption>
<thead><tr><th scope="col">Agent</th><th scope="col">CLI version</th><th scope="col">Model</th><th scope="col" class="num">Tasks</th><th scope="col" class="num">Runs per task</th><th scope="col" class="num">Runs</th><th scope="col">Started</th></tr></thead>
<tbody>${rows}</tbody></table></div>`;
}

function metricsTable(r) {
  const es = r.entries.slice().sort(byName);
  const k = es[0].metrics.k;
  const rows = [
    ["Pass rate", "Wilson 95% interval", (m) => `${pct(m.pass_rate)} ${ci(m.pass_rate_ci95)}`],
    ["Macro pass rate", "task-bootstrap 95% interval", (m) => `${pct(m.macro_pass_rate)} ${ci(m.macro_pass_rate_task_bootstrap_ci95)}`],
    [`pass@${k}`, "at least one of k runs passes", (m) => pct(m.pass_at_k)],
    [`pass^${k}`, "all k runs pass", (m) => pct(m.pass_hat_k)],
    ["Flip rate", "two runs of a task disagree", (m) => pct(m.flip_rate)],
    ["Flaky tasks", "share with both a pass and a fail", (m) => `${Math.round(m.flaky_task_fraction * m.n_tasks)} of ${m.n_tasks}`],
    ["Median cost per run", "as reported by the CLI", (m) => usd(m.median_cost_usd)],
    ["Median total tokens per run", "includes cache reads", (m) => int(m.tokens_median)],
    ["Median output tokens per run", "", (m) => int(m.output_tokens_median)],
    ["Median wall time per run", "agent process only", (m) => secs(m.wall_time_median_s)],
    ["Tokens CV within task", "mean over tasks; lower is steadier", (m) => dec(m.tokens_cv_within_task)],
    ["Approach similarity", "Jaccard over passing diffs", (m) => dec(m.approach_similarity)],
  ];
  return `<div class="tablewrap"><table class="data metrics">
<caption class="sr-only">All headline metrics</caption>
<thead><tr><th scope="col">Metric</th>${es.map((e) => `<th scope="col" class="num">${esc(agentName(e.agent))}</th>`).join("")}</tr></thead>
<tbody>${rows
    .map(
      ([name, note, f]) =>
        `<tr><th scope="row">${esc(name)}${note ? `<span class="note">${esc(note)}</span>` : ""}</th>${es
          .map((e) => `<td class="num">${esc(f(e.metrics))}</td>`)
          .join("")}</tr>`,
    )
    .join("")}</tbody></table></div>`;
}

function resultSection(r, idx) {
  const es = r.entries.slice().sort(byName);
  const id = `r-${r.date}-${r.label}`;
  const k = es[0].metrics.k;
  const title = r.lab.title || `${r.date} ${r.label}`;
  const taskIds = [...new Set(es.flatMap((e) => Object.keys(e.metrics.per_task)))].sort();
  const tasks = taskIds.map((t) => taskById[t] || { id: t, title: t });
  const maxRuns = Math.max(...es.flatMap((e) => Object.values(e.metrics.per_task).map((t) => t.n)));
  const hasCost = es.some((e) => e.metrics.median_cost_usd != null);
  const missingCost = es.filter((e) => e.metrics.median_cost_usd == null).map((e) => agentName(e.agent));

  return `<section class="result" aria-labelledby="${id}">
  <header class="result-head">
    <p class="eyebrow"><span class="mono">${esc(r.date)}</span> result set ${idx + 1} of ${data.results.length}</p>
    <h2 id="${id}">${esc(title)}</h2>
    <p class="badges">${resultBadges(r)} ${badge(`rerun-bench ${r.rerun_bench_version}`)}${r.lab.harness_commit ? " " + badge(`harness ${r.lab.harness_commit}`) : ""}</p>
    <p class="summary"><strong>In plain words:</strong> ${esc(plainSummary(r))}</p>
    <p class="links"><a href="../data/results/${esc(r.file)}">Raw JSON</a>${r.lab.source_url ? ` &middot; <a href="${esc(r.lab.source_url)}">Run records, diffs and notes</a>` : ""}${findingFor(r) ? ` &middot; <a href="../${findingUrl(findingFor(r))}">Write-up: ${esc(findingFor(r).title)}</a>` : ""}</p>
  </header>

  <h3>Setup</h3>
  ${setupTable(r)}
  ${r.lab.machine ? `<p class="small">Machine: ${esc(r.lab.machine)}.</p>` : ""}

  <h3>Pass rate</h3>
  ${intervalChart({
    id: `${id}-ci`,
    title: "Pass rate with Wilson 95% interval",
    desc: "The dot is the share of runs that passed. The bar is the 95% interval: the range of true pass rates these runs are consistent with, so a wider bar means less certainty. Agents are listed alphabetically.",
    rows: es.map((e) => ({
      label: entryLabel(e),
      sub: entrySub(e),
      est: e.metrics.pass_rate,
      lo: e.metrics.pass_rate_ci95[0],
      hi: e.metrics.pass_rate_ci95[1],
      tipNote: `${e.metrics.passes} of ${e.metrics.n_runs} runs passed`,
    })),
  })}
  <p class="verdict" role="note"><strong>Comparison:</strong> ${esc(overlapVerdict(es))}</p>

  <h3>Consistency across reruns</h3>
  ${multiDotChart({
    id: `${id}-k`,
    title: `pass^${k}, pass@1 and pass@${k}`,
    desc: `pass^${k} is the chance that all ${k} runs of a task pass (how far you can trust one run); pass@1 is the plain pass rate; pass@${k} is the chance that at least one of ${k} runs passes (what retrying until it works gets you). The gap between them is the cost of inconsistency.`,
    series: [`pass^${k}`, "pass@1", `pass@${k}`],
    rows: es.map((e) => ({
      label: entryLabel(e),
      sub: entrySub(e),
      values: [e.metrics.pass_hat_k, e.metrics.pass_rate, e.metrics.pass_at_k],
    })),
  })}

  ${consistencyGrid({
    id: `${id}-grid`,
    title: "Every run, by task",
    desc: `Each mark is one run. Columns ${Array.from({ length: maxRuns }, (_, i) => i).join(", ")} are the runs in the order they ran. A row with both a pass and a fail is a flaky task for that agent.`,
    tasks,
    agents: es.map((e) => ({
      label: entryLabel(e),
      runs: maxRuns,
      perTask: Object.fromEntries(Object.entries(e.metrics.per_task).map(([t, v]) => [t, v.outcomes])),
    })),
  })}

  <h3>Tokens and cost</h3>
  ${rangeChart({
    id: `${id}-tok`,
    title: "Total tokens per run, by task",
    desc: "Marker is the median over reruns; the line runs from the smallest to the largest run. Totals include cache reads.",
    series: es.map(entryLabel),
    rows: tasks.map((t) => ({
      label: t.id,
      values: es.map((e) => e.metrics.per_task[t.id]?.total_tokens || null),
    })),
    unit: " tokens",
  })}
  ${
    hasCost
      ? rangeChart({
          id: `${id}-cost`,
          title: "Cost per run as reported by the CLI, by task",
          desc: missingCost.length
            ? `${missingCost.join(", ")} did not report cost, so there are no marks for ${missingCost.length > 1 ? "them" : "it"}.`
            : "Marker is the median over reruns; the line runs from the cheapest to the most expensive run.",
          series: es.map(entryLabel),
          rows: tasks.map((t) => ({
            label: t.id,
            values: es.map((e) => {
              const c = e.metrics.per_task[t.id]?.cost_usd;
              return c && c.median != null ? c : null;
            }),
          })),
          fmt: (v) => (v == null ? "n/a" : `$${v.toFixed(v < 0.1 ? 3 : 2)}`),
        })
      : ""
  }

  <h3>All headline metrics</h3>
  ${metricsTable(r)}

  ${
    r.lab.notes?.length
      ? `<h3>Notes from the run</h3><ul class="notes">${r.lab.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`
      : ""
  }
</section>`;
}

function resultsPage() {
  const list = data.results;
  const index =
    list.length > 1
      ? `<nav class="toc" aria-label="Result sets"><ul>${list
          .map((r) => `<li><a href="#r-${r.date}-${r.label}"><span class="mono">${r.date}</span> ${esc(r.lab.title || r.label)}</a></li>`)
          .join("")}</ul></nav>`
      : "";
  const body = list.length
    ? list.map(resultSection).join("\n")
    : `<div class="empty"><p class="empty-title">No result sets yet.</p><p>Drop a rerun-bench JSON report into <code>data/results/</code> to publish one.</p></div>`;
  return layout({
    path: "results/",
    title: "Results",
    description: "Pass rates with confidence intervals, pass^k, flip rate and cost spread for coding agents, from repeated runs of the same tasks.",
    body: `<div class="page-head">
  <p class="eyebrow"><span class="mono">02</span> Results</p>
  <h1>Results</h1>
  <p class="lede">Each result set is one rerun-bench report: the same tasks run several times per agent, model and CLI version, scored only by each task's verifier.</p>
  <div class="rules">
    <p><strong>How to read this page.</strong> Agents are listed alphabetically, never by score. When two agents' 95% intervals overlap, this page does not call either one better. A small sample can show a gap that more runs would erase.</p>
  </div>
</div>
${index}
${body}
<section class="next" aria-labelledby="next">
  <h2 id="next">Run it yourself or add results</h2>
  <ul class="plain">
    <li>Try the harness for free with its mock agent: <code>uvx rerun-bench run --agent mock</code>. <a href="../methodology/#m-repro">Reproduce this result set</a> with a real CLI.</li>
    <li>Add a result set from your own machine: <a href="${SITE_BLOB}/CONTRIBUTING.md#submitting-results">how to submit results</a>.</li>
    <li>Seen an agent quietly get worse after an update? <a href="../regressions/">Send a regression report</a>.</li>
  </ul>
</section>`,
  });
}

// ---------------------------------------------------------------- home

// The hero instrument: every run of the latest result set as a pass/fail
// cell. The finished grid is the HTML; the fill-in is a CSS animation layered
// on top, ordered the way rerun-bench schedules runs (run 0 of every task,
// then run 1, and so on).
function heroPanel(r) {
  const es = r.entries.slice().sort(byName);
  const taskIds = [...new Set(es.flatMap((e) => Object.keys(e.metrics.per_task)))].sort();
  const runs = Math.max(...es.flatMap((e) => Object.values(e.metrics.per_task).map((t) => t.n)));
  const nT = taskIds.length;
  const total = runs * nT;
  const head1 = es
    .map((e, ai) => `${ai ? '<td class="gap"></td>' : ""}<th scope="colgroup" colspan="${runs}" class="hg-agent">${esc(agentName(e.agent))}</th>`)
    .join("");
  const head2 = es
    .map(
      (e, ai) =>
        `${ai ? '<td class="gap"></td>' : ""}` +
        Array.from({ length: runs }, (_, i) => `<th scope="col" class="hg-run"><span class="sr-only">${esc(agentName(e.agent))} run </span>${i}</th>`).join(""),
    )
    .join("");
  const rows = taskIds
    .map((t, ti) => {
      const cells = es
        .map((e, ai) => {
          const out = e.metrics.per_task[t]?.outcomes || [];
          return (
            `${ai ? '<td class="gap"></td>' : ""}` +
            Array.from({ length: runs }, (_, ri) => {
              const o = out[ri];
              if (o === undefined) return `<td><span class="hg-cell na"><span class="sr-only">no run</span></span></td>`;
              const word = o ? "pass" : "fail";
              // Interleaved order; the second agent trails by half a step.
              const i = ri * nT + ti + ai * 0.5;
              return `<td><span class="hg-cell run-mark ${word}" style="--i:${i}" data-agent="${ai}" data-tip="${esc(
                `${word}\n${agentName(e.agent)}, ${t}, run ${ri}`,
              )}"><span aria-hidden="true">${o ? "&#10003;" : "&#10005;"}</span><span class="sr-only">${word}</span></span></td>`;
            }).join("")
          );
        })
        .join("");
      return `<tr><th scope="row" class="hg-task">${esc(t)}</th>${cells}</tr>`;
    })
    .join("\n");
  const tallies = es
    .map(
      (e, ai) => `<div class="hg-tally">
  <dt>${esc(agentName(e.agent))}</dt>
  <dd><span class="hg-num"><span data-count-agent="${ai}">${e.metrics.passes}</span>/${e.metrics.n_runs}</span> passed <span class="hg-ci">95% interval: ${ciWords(e.metrics.pass_rate_ci95)}</span></dd>
</div>`,
    )
    .join("");
  return `<figure class="instrument" aria-labelledby="hg-title" data-total="${total}">
  <div class="inst-bar">
    <span class="inst-light" aria-hidden="true"></span>
    <span class="mono inst-name" id="hg-title">rerun-bench ${esc(r.rerun_bench_version)} &middot; ${esc(r.date)}${r.lab.pilot ? " pilot" : ""}</span>
    <button type="button" class="inst-replay" data-replay hidden>Replay runs</button>
  </div>
  <div class="tablewrap"><table class="hgrid" data-run="a">
    <caption class="sr-only">Every run of the latest result set: ${nT} tasks, ${runs} runs per task for each agent</caption>
    <thead><tr><td></td>${head1}</tr><tr><td class="hg-runlabel" aria-hidden="true">run</td>${head2}</tr></thead>
    <tbody>${rows}</tbody>
  </table></div>
  <dl class="hg-tallies">${tallies}</dl>
  <figcaption class="inst-cap">Each square is one run of one task, scored only by the task's verifier. <span class="run-mark pass mini" aria-hidden="true">&#10003;</span> pass <span class="run-mark fail mini" aria-hidden="true">&#10005;</span> fail. ${r.lab.pilot ? `Pilot, n=${runs} per task.` : `n=${runs} per task.`}</figcaption>
</figure>`;
}

/** GitHub repository that holds the Claude Code and Codex plugin marketplaces for the tools. */
const MARKETPLACE = "Abelo9996/open-agent-lab";

const TOOL_LIST = [
  {
    id: "nerf-watch",
    kind: "Regression detection",
    url: TOOLS.nerfWatch,
    outcome: "Find out when your coding agent quietly got worse or more expensive.",
    install: "npx nerf-watch check",
    brew: "brew install abelo9996/tap/nerf-watch",
    plugin: "nerf-watch@open-agent-lab",
    then: "Needs Node.js 20 or newer. Then <code>npx nerf-watch share</code> prints an anonymized report for the <a href=\"regressions/\">regression watch</a>.",
    facts: [
      "Reads the session logs Claude Code and Codex already write on your machine. Nothing is uploaded.",
      "Flags a different model answering than the one you picked, reasoning effort drops, a shrinking context window, cache-write jumps and failing tool calls.",
      "<code>check</code> exits with status 1 when an alert fires; <code>share</code> prints an anonymized summary and a prefilled regression report link.",
    ],
    role: "The output of nerf-watch share is what a regression report on this site contains.",
    demo: { w: 1200, h: 700, cmd: "nerf-watch check", alt: "nerf-watch check run on synthetic Claude Code logs, flagging a silent model swap from claude-opus-5 to claude-sonnet-5, a cache-write jump and a cache hit rate collapse after a CLI update" },
  },
  {
    id: "rerun-bench",
    kind: "Repeated-run benchmark",
    url: TOOLS.rerunBench,
    outcome: "Run the same coding task N times per agent and see how often it passes, how often it flips, and how much the bill varies.",
    install: "uvx rerun-bench run --agent mock",
    brew: "brew install abelo9996/tap/rerun-bench",
    plugin: "rerun-bench@open-agent-lab",
    then: "Needs <a href=\"https://docs.astral.sh/uv/\">uv</a>. The mock agent is free and finishes in seconds. <code>--agent claude</code>, <code>codex</code> or <code>opencode</code> drives a real CLI and spends credit. To keep it installed: <code>uv tool install rerun-bench</code>.",
    facts: [
      "Each run starts from a fresh temporary copy of the task, and passes only if the task's verifier exits 0.",
      "Reports pass rate with a Wilson 95% interval, pass^k, flip rate, and cost and token spread.",
      "Drives Claude Code, Codex CLI and OpenCode headlessly; a free mock agent shows the whole pipeline without spending anything.",
    ],
    role: "Produces every result on this site.",
    demo: { w: 1200, h: 700, cmd: "rerun-bench run --agent mock", alt: "rerun-bench running the free mock agent 5 times on each of 10 tasks, then printing each task's pass and fail sequence, pass rate, flip rate and cost spread" },
  },
  {
    id: "snap-back",
    kind: "Undo",
    url: TOOLS.snapBack,
    outcome: "Roll back whatever a coding agent did to your files with one command, without touching your own git history.",
    install: "npx @abelo9996/snap-back wrap -- codex",
    brew: "brew install abelo9996/tap/snap-back",
    plugin: "snap-back@open-agent-lab",
    then: "Runs Codex with snapshots on; put any agent command after <code>--</code>. Then <code>npx @abelo9996/snap-back undo</code> rolls its changes back. For everyday use: <code>npm install -g @abelo9996/snap-back</code>. Needs Node.js 20 or newer.",
    facts: [
      "Snapshots the project into a separate shadow git repository; your own <code>.git</code> is never read or written.",
      "Works with any agent, because it watches files rather than the agent.",
      "<code>undo</code> lists what it will restore and delete and asks first, and every restore can itself be undone.",
    ],
    role: "Lets you try an agent update without risking your working tree.",
    demo: { w: 1240, h: 700, cmd: "snap-back undo", alt: "snap-back wrapping an agent-like script that deletes two files and rewrites a third, then snap-back undo restoring all three" },
  },
  {
    id: "agent-fence",
    kind: "Permission policy",
    url: TOOLS.agentFence,
    outcome: "One policy file decides what every coding agent on your machine may run, read and write, and logs everything it tried.",
    install: "npm install -g @abelo9996/agent-fence",
    brew: "brew install abelo9996/tap/agent-fence",
    plugin: "agent-fence@open-agent-lab",
    then: "Then, in a project: <code>agent-fence init</code> writes a commented starter policy, and <code>agent-fence hooks install --agent claude</code> enforces it in Claude Code. Needs Node.js 20 or newer.",
    facts: [
      "Allow, ask or deny shell commands, file access and git operations from one <code>.agent-fence.toml</code>.",
      "Claude Code and Codex enforce it through their hooks; any other agent can run its commands through a wrapper.",
      "Every decision goes to a local audit log, and <code>agent-fence test</code> unit-tests the policy in CI.",
    ],
    role: "Keeps benchmark and everyday runs inside rules you can read and test.",
    demo: { w: 1400, h: 600, cmd: "agent-fence check", alt: "agent-fence check denying \"cd app && git push --force\" and \"cat .env\" with the matching rule and reason, and allowing \"npm test\"" },
  },
  {
    id: "launch-day-kit",
    kind: "Launch tooling",
    url: TOOLS.launchDayKit,
    outcome: "Ship a companion repo within hours of an AI platform launch.",
    install: "git clone https://github.com/Abelo9996/launch-day-kit",
    then: "Then <code>cd launch-day-kit &amp;&amp; node bin/new-launch.mjs --list</code> lists the templates. Needs Node.js 22 or newer; nothing to install.",
    facts: [
      "A playbook with a T-minus and T-plus checklist, naming rules and a README pattern.",
      "Five tested templates: awesome-list, terminal UI, desktop app, plugin market and model router.",
      "A zero-dependency scaffolder fills placeholders and commits; <code>npm run rehearse</code> times every template end to end.",
    ],
    role: "Works to the same clock as the launch-day plan on this site: hours, not weeks.",
    demo: { w: 1300, h: 700, cmd: "node bin/new-launch.mjs", alt: "launch-day-kit scaffolding a model-router repo for a fake platform, then installing it and passing all 10 of its tests in seconds" },
  },
];

function toolSection(t, i) {
  const n = `3.${i + 1}`;
  return `<section class="toolsec${i % 2 ? " flip" : ""}" id="${t.id}" aria-labelledby="${t.id}-h">
  <div class="toolsec-text">
    <p class="eyebrow"><span class="mono">${n}</span> ${esc(t.kind)}</p>
    <h3 id="${t.id}-h" class="tool-name"><a class="anchor" href="#${t.id}"><span class="mono">${t.id}</span><span class="anchor-mark" aria-hidden="true">#</span></a></h3>
    <p class="outcome">${esc(t.outcome)}</p>
    <div class="cmd"><pre><code>${esc(t.install)}</code></pre><button type="button" class="copy" data-copy hidden aria-label="Copy the ${t.id} command">Copy</button></div>
    ${t.then ? `<p class="cmd-then small">${t.then}</p>` : ""}
    ${t.brew ? `<p class="cmd-brew small">Homebrew (macOS and Linux): <code>${esc(t.brew)}</code></p>` : ""}
    ${t.plugin ? `<p class="cmd-plugin small">Claude Code plugin: <code>/plugin install ${esc(t.plugin)}</code> after <code>/plugin marketplace add ${MARKETPLACE}</code>. Codex: <code>codex plugin add ${esc(t.plugin)}</code> from the same marketplace.</p>` : ""}
    <ul class="facts">${t.facts.map((f) => `<li>${f}</li>`).join("")}</ul>
    <p class="tool-role">${esc(t.role)}</p>
    <p class="tool-links"><a class="go" href="${t.url}">Repository</a> <a class="go" href="${t.url}/blob/main/README.md">README</a></p>
  </div>
  <figure class="demo">
    <div class="demo-bar"><span class="mono">$ ${esc(t.demo.cmd)}</span><button type="button" class="demo-toggle" data-demo-toggle hidden aria-pressed="false">Pause</button></div>
    <div class="demo-frame" style="aspect-ratio:${t.demo.w} / ${t.demo.h}"><img src="assets/demos/${t.id}.webp" data-gif="assets/demos/${t.id}.gif" width="${t.demo.w}" height="${t.demo.h}" loading="lazy" decoding="async" alt="${esc(t.demo.alt)}"></div>
    <figcaption class="small">Terminal recording from the repository. It plays while on screen; with reduced motion on, the still frame stays until you press Play. <a href="assets/demos/${t.id}.gif">Open the animated demo</a>.</figcaption>
  </figure>
</section>`;
}

function homePage() {
  // The home hero features the newest result set, skipping any with lab.feature
  // set to false (e.g. single-agent mining runs that read better on the results
  // page than as the headline comparison). Every set still lists under Results.
  const latest = data.results.find((r) => r.lab.feature !== false) || data.results[0];
  let latestBlock = `<div class="empty"><p class="empty-title">No results published yet.</p></div>`;
  if (latest) {
    const es = latest.entries.slice().sort(byName);
    const k = es[0].metrics.k;
    const tiles = es
      .map(
        (e) => `<div class="tile">
  <p class="tile-name">${esc(agentName(e.agent))}</p>
  <p class="tile-sub mono">${esc(entrySub(e))}</p>
  <dl>
    <div><dt>pass rate</dt><dd>${pct(e.metrics.pass_rate)} <span>${ci(e.metrics.pass_rate_ci95)}</span></dd></div>
    <div><dt>pass^${k}</dt><dd>${pct(e.metrics.pass_hat_k)}</dd></div>
    <div><dt>flip rate</dt><dd>${pct(e.metrics.flip_rate)}</dd></div>
    <div><dt>median tokens</dt><dd>${compact(e.metrics.tokens_median)}</dd></div>
  </dl>
</div>`,
      )
      .join("");
    latestBlock = `<div class="latest">
  <div class="latest-head">
    <p class="mono small">${esc(latest.date)}</p>
    <h3>${esc(latest.lab.title || latest.label)}</h3>
    <p class="badges">${resultBadges(latest)}</p>
    <p class="summary"><strong>In plain words:</strong> ${esc(plainSummary(latest))}</p>
  </div>
  ${intervalChart({
    id: "home-ci",
    title: "Pass rate with Wilson 95% interval",
    rows: es.map((e) => ({
      label: entryLabel(e),
      sub: e.model,
      est: e.metrics.pass_rate,
      lo: e.metrics.pass_rate_ci95[0],
      hi: e.metrics.pass_rate_ci95[1],
      tipNote: `${e.metrics.passes} of ${e.metrics.n_runs} runs passed`,
    })),
    compactView: true,
  })}
  <div class="tiles">${tiles}</div>
  ${metricKey(k)}
  <p class="verdict" role="note">${esc(overlapVerdict(es))}</p>
  ${findingFor(latest) ? `<p class="finding-link"><strong>Write-up:</strong> <a href="${findingUrl(findingFor(latest))}">${esc(findingFor(latest).title)}</a></p>` : ""}
  <p><a class="more" href="results/">Full results, per-task grid and table view</a></p>
</div>`;
  }

  return layout({
    path: "",
    title: "Home",
    description: "Independent, reproducible evaluation of coding agents. Same tasks, many runs, intervals shown.",
    // With many runs per task the hero panel is too wide to sit beside the text.
    body: `<section class="hero${latest && latest.entries.reduce((n, e) => n + (e.metrics.k || 0), 0) > 12 ? " hero-wide" : ""}">
  <div class="hero-text">
    <p class="eyebrow"><span class="mono">01</span> open agent lab</p>
    <h1>Coding agents, measured more than once.</h1>
    <p class="lede">An independent lab that runs the same coding tasks many times on agents such as Claude Code and Codex CLI, and publishes how often they pass, how often the result flips between runs, and what a run costs. One run is an anecdote; this site shows the spread and the uncertainty.</p>
    <p class="hero-links"><a class="button" href="results/">See results</a> <a class="button ghost" href="methodology/">How runs are scored</a></p>
    <p class="jump-label small" id="jump-label">Free, open-source tools the lab is built on:</p>
    <ul class="jump" aria-labelledby="jump-label">${TOOL_LIST.map((t) => `<li><a href="#${t.id}" class="mono">${t.id}</a></li>`).join("")}</ul>
  </div>
  ${latest ? heroPanel(latest) : ""}
</section>

<section aria-labelledby="latest">
  ${sectionHead("02", "Latest", "Latest result set", "latest")}
  ${latestBlock}
</section>

<section aria-labelledby="tools" class="tools-wrap">
  ${sectionHead("03", "Tools", "The tools behind the lab", "tools")}
  <p>All five are open source and run on your own machine. Each one starts with a command you can paste as is. Each section has a stable link, such as <a class="nowrap" href="#nerf-watch">#nerf-watch</a>.</p>
  ${TOOL_LIST.map(toolSection).join("\n")}
</section>

<section aria-labelledby="contribute">
  ${sectionHead("04", "Contribute", "Contribute data", "contribute")}
  <div class="cols">
    <div class="col">
      <h3>Results</h3>
      <ol class="steps">
        <li>Run <a href="${TOOLS.rerunBench}">rerun-bench</a> with at least 3 runs per task: <code>uvx rerun-bench run --agent claude --runs 3 --out results/</code>.</li>
        <li>Generate the JSON report: <code>uvx rerun-bench report results/ --format json -o report.json</code>.</li>
        <li>Save it as <code>data/results/&lt;YYYY-MM-DD&gt;-&lt;label&gt;.json</code> and open a pull request with the CLI versions, models and machine.</li>
      </ol>
    </div>
    <div class="col">
      <h3>Regression reports</h3>
      <ol class="steps">
        <li>Run <code>npx nerf-watch share</code>.</li>
        <li>Read the JSON it prints. It holds aggregate numbers only.</li>
        <li>Open the prefilled <a href="${ISSUE_FORM}">regression report</a> link it prints and submit it.</li>
      </ol>
    </div>
  </div>
  <p><a href="${SITE_BLOB}/CONTRIBUTING.md">Required metadata and review steps</a></p>
</section>`,
  });
}

// ---------------------------------------------------------------- methodology

function methodologyPage() {
  const taskRows = data.tasks.tasks
    .map(
      (t) =>
        `<tr><th scope="row"><span class="mono">${esc(t.id)}</span></th><td>${esc(t.title)}</td><td>${t.tags.map((g) => `<span class="tag">${esc(g)}</span>`).join(" ")}</td><td class="num">${t.timeout_s ?? "n/a"} s</td></tr>`,
    )
    .join("");
  const metrics = [
    ["Pass rate", "Passing runs divided by all runs. A run passes only if the task's verify.py exits 0. The agent's exit code and its own claims of success are recorded but never scored."],
    ["Wilson 95% interval", "The range of pass rates consistent with the observed runs. Unlike the normal approximation, it behaves at 0% and 100% and at small n. With 30 runs and 30 passes the interval is still 89% to 100%."],
    ["Macro pass rate and task-bootstrap interval", "The mean of per-task pass rates, with an interval from resampling tasks. It reflects uncertainty about the task population, which the pooled Wilson interval ignores. Use it when comparing agents across the suite."],
    ["pass@k", "Chance that at least one of k runs of a task passes (Chen et al. 2021). What you get if you retry until it works."],
    ["pass^k", "Chance that all k runs of a task pass (Yao et al. 2024). What you get if you run the agent once and trust the result."],
    ["Flip rate", "Chance that two runs of the same task disagree, averaged over tasks. 0 means every task always passes or always fails."],
    ["Flaky task fraction", "Share of tasks with at least one pass and at least one fail. Coarser than flip rate and grows with n."],
    ["Cost, tokens, wall time", "Medians per run as the CLI reports them. A value the CLI does not report is null and shown as not reported, never as zero. Wall time covers the agent process only."],
    ["Within-task CV", "Coefficient of variation across reruns of one task, averaged over tasks. It measures how steady one agent is, not how different the tasks are."],
    ["Approach similarity", "Mean Jaccard similarity of changed lines across passing runs of a task. 1.0 means every passing run made the same edit."],
  ]
    .map(([t, d]) => `<div><dt>${esc(t)}</dt><dd>${esc(d)}</dd></div>`)
    .join("");
  return layout({
    path: "methodology/",
    title: "Methodology",
    description: "How runs are isolated and scored, what each metric means, the task suite, and known limitations.",
    body: `<div class="page-head">
  <p class="eyebrow"><span class="mono">03</span> Methodology</p>
  <h1>Methodology</h1>
  <p class="lede">Every number on this site is produced by <a href="${TOOLS.rerunBench}">rerun-bench</a>. The formulas, with unit tests, are in <a href="${TOOLS.metrics}">docs/METRICS.md</a>. This page summarizes them.</p>
</div>

<section aria-labelledby="m-run">
  ${sectionHead("3.1", "Runs", "What one run is", "m-run")}
  <ol class="steps">
    <li>rerun-bench copies the task's starting workspace into a fresh temporary directory. Nothing carries over between runs.</li>
    <li>It starts the agent CLI headlessly in that directory with the task prompt, and records wall time, exit status, token counts, cost when the CLI reports it, the CLI version, the model and the final diff.</li>
    <li>The task's verifier runs against the workspace. The run passes if and only if the verifier exits 0.</li>
  </ol>
  <p>Runs are interleaved: run 0 of every task, then run 1 of every task, and so on, so a provider-side change in the middle of a session spreads across tasks instead of landing on whichever task ran last.</p>
</section>

<section aria-labelledby="m-metrics">
  ${sectionHead("3.2", "Metrics", "What each metric means", "m-metrics")}
  <dl class="defs">${metrics}</dl>
  <p><code>pass^k</code> is never higher than pass@1, and pass@1 is never higher than <code>pass@k</code>. The gap between pass@k and pass^k is the cost of inconsistency. <a href="${TOOLS.metrics}">Full formulas in METRICS.md</a>.</p>
</section>

<section aria-labelledby="m-compare">
  ${sectionHead("3.3", "Comparisons", "How agents are compared", "m-compare")}
  <ul class="plain">
    <li>Agents are listed alphabetically on every page. There is no rank column.</li>
    <li>When two agents' 95% intervals overlap, the site states that the data does not show a difference. It does not call either one better.</li>
    <li>Statistical tests between result sets (Fisher exact per task, paired task-level bootstrap) are planned in rerun-bench and not yet run. Until they are, non-overlapping intervals are reported as such and nothing more.</li>
    <li>Results from different dates, machines or CLI versions are separate result sets and are not pooled.</li>
  </ul>
</section>

<section aria-labelledby="m-tasks">
  ${sectionHead("3.4", "Tasks", "Task suite", "m-tasks")}
  <p>${esc(data.tasks.suite)}: ${data.tasks.tasks.length} small, verifiable Python tasks. Each has a prompt, a starting workspace, a reference solution and a verifier script. They cover precise edits, bug fixes, implementing to a spec, refactors that must preserve behavior, following repository instructions, and writing tests that must catch injected bugs. <a href="${esc(data.tasks.source_url)}">Task sources</a>.</p>
  <div class="tablewrap"><table class="data">
    <caption class="sr-only">Tasks in the suite</caption>
    <thead><tr><th scope="col">Task</th><th scope="col">What it asks</th><th scope="col">Tags</th><th scope="col" class="num">Timeout</th></tr></thead>
    <tbody>${taskRows}</tbody>
  </table></div>
</section>

<section aria-labelledby="m-iso">
  ${sectionHead("3.5", "Isolation", "How runs are isolated", "m-iso")}
  <ul class="plain">
    <li><strong>Workspace.</strong> Each run gets its own temporary copy of the task workspace. Task workspaces are not git repositories.</li>
    <li><strong>Personal configuration.</strong> For Claude Code, rerun-bench loads only project and local settings (<code>--setting-sources project,local --strict-mcp-config</code>), so the user's hooks, plugins and MCP servers do not apply. For Codex CLI it passes <code>--ignore-user-config</code>, so the model, reasoning effort and hooks in the user's config do not apply. Authentication still works.</li>
    <li><strong>Nested sessions.</strong> When rerun-bench itself runs inside an agent session, that session's environment variables are removed before the measured agent starts.</li>
    <li><strong>Permissions.</strong> The agent runs with file-edit and shell permissions inside the temporary directory, like any unattended agent session.</li>
  </ul>
</section>

<section aria-labelledby="m-limits">
  ${sectionHead("3.6", "Limits", "Known limitations", "m-limits")}
  <ul class="plain">
    <li><strong>Small samples.</strong> At 3 runs per task, one failure moves a task's pass rate by 33 points. Results marked pilot are checks that the harness works, not leaderboards.</li>
    <li><strong>Small tasks.</strong> Ten short Python tasks do not represent work in large repositories, other languages, or long sessions.</li>
    <li><strong>One machine, one day.</strong> Each result set comes from one machine at one time. Provider-side load, routing and model changes are outside the lab's control.</li>
    <li><strong>Cost semantics.</strong> Claude Code reports cost at list prices even on a subscription login, where it is quota used rather than money billed. Codex CLI reports tokens only.</li>
    <li><strong>Model identity.</strong> <code>codex exec --json</code> does not report the model, so it is recorded from the <code>--model</code> flag passed to the CLI.</li>
    <li><strong>Token counts.</strong> Totals include cache reads, which dominate the count for both CLIs. Turn counts are not comparable across CLIs and are not shown.</li>
    <li><strong>Approach similarity.</strong> Line-level Jaccard is sensitive to formatting and ignores line order. It signals variability, not code quality.</li>
    <li><strong>Concurrency.</strong> In the pilot the two agents ran at the same time on one machine, which can affect wall time.</li>
  </ul>
</section>

<section aria-labelledby="m-repro">
  ${sectionHead("3.7", "Reproduce", "Reproduce a result set", "m-repro")}
  <pre><code>uv tool install rerun-bench
rerun-bench run --agent claude --tasks all --runs 3 --out results/ --run-id claude --yes
rerun-bench run --agent codex --model &lt;model&gt; --tasks all --runs 3 --out results/ --run-id codex --yes
rerun-bench report results/ --format json -o report.json</code></pre>
  <p>Real runs spend API credit or subscription quota. Start with <code>--tasks edit-config --runs 2</code>.</p>
</section>`,
  });
}

// ---------------------------------------------------------------- regressions

const SIGNAL_LABEL = {
  "model-reroute": "Different model answered",
  "effort-drop": "Reasoning effort dropped",
  "context-shrink": "Context window shrank",
  "cache-writes": "Cache writes jumped",
  "cache-hit-rate": "Cache hit rate fell",
  "tool-errors": "Tool errors rose",
  tokens: "Token use changed",
  cost: "Cost changed",
  "pass-rate": "Pass rate changed",
  other: "Other",
};
const STATUS_LABEL = {
  open: "Open",
  confirmed: "Confirmed",
  "not-reproduced": "Not reproduced",
  explained: "Explained",
};

/** Effect size in the unit the aggregator used for the signal. */
function effectText(v, unit) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const signed = (x, d) => `${x > 0 ? "+" : x < 0 ? "-" : ""}${Math.abs(x).toFixed(d)}`;
  if (unit === "ratio") return `${v.toFixed(2)}x`;
  if (unit === "pp") return `${signed(v * 100, 1)} pp`;
  if (unit === "levels") return `${signed(v, 0)} level${Math.abs(v) === 1 ? "" : "s"}`;
  if (unit === "share") return `${(v * 100).toFixed(1)}% of turns`;
  return "n/a";
}

const EFFECT_NOTE = {
  ratio: "after divided by before",
  pp: "after minus before, in percentage points",
  levels: "change in effort level",
  share: "share of turns answered by another model",
};

function aggregateTable(rows) {
  const body = rows
    .map((a) => {
      const versions = a.cli_before.length ? `${a.cli_before.join(", ")} to ${a.cli_version}` : a.cli_version;
      const model = a.served_models.length ? `${a.model} (served: ${a.served_models.join(", ")})` : a.model;
      const issues = a.issues.map((x) => `<a href="${esc(x.url)}">#${esc(x.number)}</a>`).join(", ");
      const span = a.first_seen ? `${a.first_seen} to ${a.last_seen || a.first_seen}` : "n/a";
      const effect = effectText(a.effect_median, a.effect_unit);
      const effectTitle = a.effect_unit ? ` title="${esc(`Median of ${a.reports} report(s); ${EFFECT_NOTE[a.effect_unit]}`)}"` : "";
      return `<tr><th scope="row">${esc(agentName(a.agent))}</th><td class="mono">${esc(model)}</td><td class="mono">${esc(versions)}</td><td>${esc(
        SIGNAL_LABEL[a.signal] || a.signal,
      )}</td><td class="num">${esc(a.reports)}</td><td class="num mono"${effectTitle}>${esc(effect)}</td><td class="mono">${esc(span)}</td><td>${issues}</td></tr>`;
    })
    .join("");
  return `<div class="tablewrap"><table class="data">
<caption class="sr-only">Community regression reports, aggregated per agent, CLI version, model and signal</caption>
<thead><tr><th scope="col">Agent</th><th scope="col">Model</th><th scope="col">CLI version</th><th scope="col">Signal</th><th scope="col" class="num">Independent reports</th><th scope="col" class="num">Median effect</th><th scope="col">Seen</th><th scope="col">Source issues</th></tr></thead>
<tbody>${body}</tbody></table></div>
<p class="small">Independent reports counts distinct GitHub accounts; one account counts once per row however many issues it files. Median effect: ratios are after divided by before, pp is the change in percentage points, and model rerouting is the share of turns another model answered. A row with one report is one person's data.</p>`;
}

function reviewedTable(reports) {
  return `<div class="tablewrap"><table class="data">
<caption class="sr-only">Reviewed regression reports</caption>
<thead><tr><th scope="col">Reported</th><th scope="col">Agent</th><th scope="col">Model</th><th scope="col">CLI change</th><th scope="col">Signal</th><th scope="col">Summary</th><th scope="col" class="num">Reports</th><th scope="col">Status</th></tr></thead>
<tbody>${reports
    .map(
      (r) => `<tr><td class="mono">${esc(r.reported_at)}</td><th scope="row">${esc(agentName(r.agent))}</th><td class="mono">${esc(r.model || "n/a")}</td><td class="mono">${esc(
        `${r.cli_before || "?"} to ${r.cli_after || "?"}`,
      )}</td><td>${esc(SIGNAL_LABEL[r.signal])}</td><td>${esc(r.summary)} <a href="${esc(r.issue_url)}">issue</a></td><td class="num">${esc(r.independent_reports)}</td><td><span class="status st-${esc(r.status)}">${esc(
        STATUS_LABEL[r.status],
      )}</span></td></tr>`,
    )
    .join("")}</tbody></table></div>`;
}

function regressionsPage() {
  const reports = data.regressions.slice().sort((a, b) => b.reported_at.localeCompare(a.reported_at));
  const rows = data.regressionAggregates;
  const empty = `<div class="empty">
  <svg class="empty-art" viewBox="0 0 240 64" aria-hidden="true" focusable="false"><line x1="0" y1="40" x2="240" y2="40" class="empty-base"/><path d="M0 40 H60 L66 34 L72 46 L78 40 H240" class="empty-line"/><circle cx="210" cy="40" r="4" class="empty-dot"/></svg>
  <p class="empty-title">No regression reports yet.</p>
  <p>When reports arrive, each agent, CLI version, model and signal is listed here with the number of independent reports, the median effect size, the dates it was seen and links to the source issues.</p>
  <p><a class="button" href="${ISSUE_FORM}">Report a suspected regression</a></p>
</div>`;
  const list =
    !rows.length && !reports.length
      ? empty
      : [rows.length ? aggregateTable(rows) : "", reports.length ? `<h3>Reviewed reports</h3>\n${reviewedTable(reports)}` : ""].filter(Boolean).join("\n");
  return layout({
    path: "regressions/",
    title: "Regression watch",
    description: "Reports of silent changes in coding agents: model rerouting, effort drops, token and cost jumps, collected from anonymized nerf-watch reports.",
    body: `<div class="page-head">
  <p class="eyebrow"><span class="mono">04</span> Regression watch</p>
  <h1>Regression watch</h1>
  <p class="lede">A place to collect evidence when an agent quietly gets worse or more expensive after an update, so a change that hits many people shows up as many matching reports instead of scattered complaints.</p>
  <p><a class="button" href="${ISSUE_FORM}">Report a suspected regression</a></p>
</div>

<section aria-labelledby="g-nw">
  ${sectionHead("4.1", "nerf-watch", "Where the evidence comes from", "g-nw")}
  <p><a href="${TOOLS.nerfWatch}">nerf-watch</a> reads the session logs that Claude Code and Codex already write on your machine and compares your own history across CLI versions and over time. It flags changes you did not make:</p>
  <ul class="plain">
    <li>a different model answered than the one you picked;</li>
    <li>reasoning effort dropped;</li>
    <li>the context window shrank;</li>
    <li>cache writes per turn jumped, or the cache hit rate collapsed, after a CLI update;</li>
    <li>tool calls started failing more often.</li>
  </ul>
  <p>Install command and a terminal recording: <a href="../#nerf-watch">nerf-watch on the home page</a>.</p>
  <p>Everything runs locally. <code>nerf-watch share</code> builds the report from structured fields only: detector, severity, agent, model ids, CLI versions, dates, sample counts and before and after values. It contains no prompts, responses, tool output, file paths, project names, session ids, or user or host names, and it makes no network request. It prints exactly what would be shared before you share it.</p>
</section>

<section aria-labelledby="g-how">
  ${sectionHead("4.2", "Report", "How to report", "g-how")}
  <ol class="steps">
    <li>Run <code>npx nerf-watch share</code> (Node.js 20 or newer). It prints the anonymized JSON and a link to a prefilled report in the open-agent-lab repository. Add <code>--open</code> to open the link in your browser.</li>
    <li>Read the JSON. The issue is public.</li>
    <li>Open the link, say what you observed, and submit. If the JSON was too long for the link, paste it into the report field.</li>
  </ol>
  <p>Every hour, the site build reads open issues labeled <code>regression-report</code> in the <a href="${REGRESSION_REPO}/issues?q=is%3Aissue+is%3Aopen+label%3Aregression-report">open-agent-lab repository</a>. It validates the JSON against a strict schema, rejects anything that is not valid, too large, or contains path-like or email-like text, and aggregates the findings per agent, CLI version, model and signal. Closing an issue removes it from the table within the hour.</p>
</section>

<section aria-labelledby="g-list">
  ${sectionHead("4.3", "Reports", "Reported regressions", "g-list")}
  ${list}
</section>`,
  });
}

// ---------------------------------------------------------------- launches

function launchesPage() {
  const ls = data.launches.slice().sort((a, b) => b.announced_at.localeCompare(a.announced_at));
  const hours = (a, b) => (a && b ? `${((Date.parse(b) - Date.parse(a)) / 36e5).toFixed(1)} h` : "n/a");
  const table = ls.length
    ? `<div class="tablewrap"><table class="data">
<caption class="sr-only">Launch-day result sets</caption>
<thead><tr><th scope="col">Model</th><th scope="col">Vendor</th><th scope="col">Announced</th><th scope="col">Status</th><th scope="col" class="num">Published after</th><th scope="col">Results</th></tr></thead>
<tbody>${ls
        .map(
          (l) => `<tr><th scope="row" class="mono">${esc(l.model)}</th><td>${esc(l.vendor)}</td><td class="mono">${esc(l.announced_at.replace("T", " "))}</td><td>${esc(l.status)}</td><td class="num">${hours(
            l.announced_at,
            l.published_at,
          )}</td><td>${l.results_file ? `<a href="../results/#r-${esc(l.results_file.replace(/\.json$/, ""))}">result set</a>` : "pending"}</td></tr>`,
        )
        .join("")}</tbody></table></div>`
    : `<div class="empty">
  <svg class="empty-art" viewBox="0 0 240 64" aria-hidden="true" focusable="false"><line x1="0" y1="40" x2="240" y2="40" class="empty-base"/>${Array.from({ length: 24 }, (_, i) => `<line x1="${6 + i * 10}" x2="${6 + i * 10}" y1="${i % 6 === 0 ? 30 : 35}" y2="40" class="empty-tick"/>`).join("")}<circle cx="6" cy="40" r="4" class="empty-dot"/></svg>
  <p class="empty-title">No launch-day results yet.</p>
  <p>The first one will appear here after the next major model launch, with the time from announcement to publication.</p>
</div>`;
  return layout({
    path: "launches/",
    title: "Launch day",
    description: "Plan for publishing rerun-bench numbers within 24 hours of major model launches.",
    body: `<div class="page-head">
  <p class="eyebrow"><span class="mono">05</span> Launch day</p>
  <h1>Launch-day results</h1>
  <p class="lede">The plan: publish rerun-bench numbers for a new model within 24 hours of its launch, so there is a measured, reproducible data point next to the announcement.</p>
</div>

<section aria-labelledby="l-plan">
  ${sectionHead("5.1", "Plan", "What happens after a launch", "l-plan")}
  <ol class="timeline">
    <li><span class="mono t">T+0</span><div><strong>Announcement.</strong> The model becomes available in at least one supported CLI (Claude Code, Codex CLI, OpenCode). The announcement time is recorded.</div></li>
    <li><span class="mono t">T+0 to 2 h</span><div><strong>Setup.</strong> The current CLI version is pinned. The new model and the model it replaces are run with the same CLI version, the same harness commit and the same machine.</div></li>
    <li><span class="mono t">T+2 to 20 h</span><div><strong>Runs.</strong> The full default suite, at least 5 runs per task, interleaved. Failures are checked against their diffs before publishing, and any failure caused by the harness or the environment is reported, not hidden.</div></li>
    <li><span class="mono t">by T+24 h</span><div><strong>Publish.</strong> The report goes into <code>data/results/</code> with <code>lab.launch</code> set, run records and diffs are linked, and the publication time is recorded below.</div></li>
  </ol>
  <p>If 24 hours is not enough to finish the runs, the result set is published late and the delay is shown. Launch-day numbers follow the same rules as every other result: intervals shown, no ranking when they overlap.</p>
  <p>For shipping a companion repository on the same clock, see <a href="../#launch-day-kit">launch-day-kit</a>.</p>
</section>

<section aria-labelledby="l-follow">
  ${sectionHead("5.2", "Follow", "Follow along or run it yourself", "l-follow")}
  <ul class="plain">
    <li>Watch the <a href="${REPO}">repository on GitHub</a>: each launch-day result set lands as a commit to <code>data/results/</code>.</li>
    <li>Run the same suite on a new model yourself with <a href="../#rerun-bench">rerun-bench</a> and <a href="${SITE_BLOB}/CONTRIBUTING.md#submitting-results">submit the report</a>.</li>
  </ul>
</section>

<section aria-labelledby="l-list">
  ${sectionHead("5.3", "Log", "Launch-day log", "l-list")}
  ${table}
</section>`,
  });
}

// ---------------------------------------------------------------- findings

// Write-ups of one result set each, in plain first person. Numbers are read
// from the result file, so the prose cannot drift from the data.
const FINDINGS = [
  {
    slug: "2026-10-rerun-pilot",
    result: "2026-10-03-pilot.json",
    published: "2026-10-05",
    title: "Same task, 3 runs: Codex passed and failed on 2 of 10 tasks, Claude Code on 0",
    description:
      "A 60-run pilot: Claude Code and Codex CLI on the same 10 coding tasks, 3 runs each. What reruns showed, the two Codex failures, and what 3 runs per task cannot show.",
    image: { file: "findings/2026-10-rerun-pilot.png", w: 1200, h: 630 },
    render: pilotPost,
  },
  {
    slug: "2026-10-rerun-10x",
    result: "2026-10-06-rerun-10x.json",
    published: "2026-10-07",
    title: "Same task, 10 runs: Codex CLI reported edits it never made in 3 of 100 runs",
    description:
      "200 runs: Claude Code and Codex CLI on the same 10 coding tasks, 10 runs each. Claude Code passed all 100. Codex passed 96, and all 4 failures were clean exits with no file changed.",
    image: { file: "findings/2026-10-rerun-10x.png", w: 1200, h: 630 },
    render: tenRunPost,
  },
];
const findingFor = (r) => FINDINGS.find((f) => f.result === r.file);
const findingUrl = (f) => `findings/${f.slug}/`;

function pilotPost(f) {
  const r = data.results.find((x) => x.file === f.result);
  if (!r) throw new Error(`finding ${f.slug}: no result set ${f.result}`);
  const es = r.entries.slice().sort(byName);
  const cc = es.find((e) => e.agent === "claude");
  const cx = es.find((e) => e.agent === "codex");
  const m = { cc: cc.metrics, cx: cx.metrics };
  const k = m.cc.k;
  const flaky = Object.entries(m.cx.per_task).filter(([, t]) => t.outcomes.some(Boolean) && !t.outcomes.every(Boolean));
  const flakyCc = Object.values(m.cc.per_task).filter((t) => t.outcomes.some(Boolean) && !t.outcomes.every(Boolean));
  // The headline in the title, checked against the data on every build.
  if (flaky.length !== 2 || flakyCc.length !== 0 || m.cx.n_tasks !== 10 || k !== 3) {
    throw new Error(`finding ${f.slug}: the title no longer matches ${f.result}`);
  }
  const nTasks = m.cc.n_tasks;
  const nRuns = m.cc.n_runs + m.cx.n_runs;
  const allTasks = Object.keys(m.cc.per_task).sort().map((t) => taskById[t] || { id: t, title: t });
  const flakyTasks = flaky.map(([t]) => taskById[t] || { id: t, title: t });
  const repro = TOOLS.rerunBench;
  const pilotDir = r.lab.source_url;

  const rows = [
    ["Runs passed", (x) => `${x.passes} of ${x.n_runs}`],
    ["Pass rate, Wilson 95% interval", (x) => `${pct(x.pass_rate)} ${ci(x.pass_rate_ci95)}`],
    [`pass@${k}: at least one of ${k} runs passes`, (x) => pct(x.pass_at_k)],
    [`pass^${k}: all ${k} runs pass`, (x) => pct(x.pass_hat_k)],
    ["Flip rate: two runs of a task disagree", (x) => pct(x.flip_rate)],
    ["Tasks with both a pass and a fail", (x) => `${Math.round(x.flaky_task_fraction * x.n_tasks)} of ${x.n_tasks}`],
  ];
  const table = `<div class="tablewrap"><table class="data metrics post-table">
<caption class="sr-only">Headline numbers for the pilot</caption>
<thead><tr><th scope="col">Metric</th><th scope="col" class="num">Claude Code</th><th scope="col" class="num">Codex</th></tr></thead>
<tbody>${rows.map(([name, fn]) => `<tr><th scope="row">${esc(name)}</th><td class="num">${esc(fn(m.cc))}</td><td class="num">${esc(fn(m.cx))}</td></tr>`).join("")}</tbody></table></div>`;

  const body = `<article class="post" aria-labelledby="post-title">
<header class="page-head post-head">
  <p class="eyebrow"><span class="mono">${esc(f.published)}</span> <a href="../">Findings</a></p>
  <h1 id="post-title">${esc(f.title)}</h1>
  <p class="byline small">By Abel Yagubyan. Data: <a href="../../results/#r-${r.date}-${r.label}">the ${esc(r.date)} pilot</a> (<a href="../../data/results/${esc(r.file)}">raw JSON</a>, <a href="${esc(pilotDir)}">run records and diffs</a>).</p>
</header>

<p class="lede">On ${esc(r.date)} I gave Claude Code and Codex CLI the same ${nTasks} small coding tasks and ran each task ${k} times per agent, ${nRuns} runs in all. Claude Code passed all ${m.cc.n_runs} of its runs. Codex CLI passed ${m.cx.passes} of ${m.cx.n_runs}, and its two failures were on two different tasks that it passed on the other two tries. So for 2 of ${nTasks} tasks, whether Codex could do the task depended on which run you looked at. With only ${k} runs per task the two agents' pass-rate intervals overlap, so this pilot does not show that either one is more reliable than the other.</p>

<h2 id="setup">What I ran</h2>
<p>I build evaluation tools, and this pilot used one of them, <a href="${repro}">rerun-bench</a>. Each run starts from a fresh copy of the task's files, drives the agent's CLI headlessly, and is scored only by the task's own verifier script. The agent's exit code and its own claims of success are recorded but never scored.</p>
<ul class="plain">
  <li>Claude Code ${esc(cc.cli_version.replace(/ \(Claude Code\)$/, ""))} with its default model, which it reported as <code>${esc(cc.model)}</code>.</li>
  <li>Codex CLI ${esc(cx.cli_version.replace(/^codex-cli /, ""))} with <code>${esc(cx.model)}</code>, the model that version picks when none is configured.</li>
  <li>${nTasks} tasks, such as fixing the bug behind a failing test, implementing an LRU cache from its docstrings, renaming a function across a package, and following a repository's AGENTS.md. Runs were interleaved: run 0 of every task, then run 1, then run 2.</li>
  <li>One Mac (${esc(r.lab.machine)}), between 08:16 and 08:25 UTC. Both agents ran at the same time, each one run at a time. Harness: rerun-bench ${esc(r.rerun_bench_version)} at commit ${esc(r.lab.harness_commit)}.</li>
</ul>

<h2 id="numbers">The numbers</h2>
${intervalChart({
  id: "post-ci",
  title: "Pass rate with Wilson 95% interval",
  desc: "The dot is the share of runs that passed; the bar is the 95% interval. The bars overlap.",
  rows: es.map((e) => ({
    label: entryLabel(e),
    sub: e.model,
    est: e.metrics.pass_rate,
    lo: e.metrics.pass_rate_ci95[0],
    hi: e.metrics.pass_rate_ci95[1],
    tipNote: `${e.metrics.passes} of ${e.metrics.n_runs} runs passed`,
  })),
})}
${table}
${consistencyGrid({
  id: "post-grid",
  title: "Every run, by task",
  desc: "Each mark is one run, in the order they ran. The two Codex CLI rows with a fail are the two flaky tasks.",
  tasks: allTasks,
  agents: es.map((e) => ({
    label: entryLabel(e),
    runs: k,
    perTask: Object.fromEntries(Object.entries(e.metrics.per_task).map(([t, v]) => [t, v.outcomes])),
  })),
})}

<h2 id="failures">The two Codex failures</h2>
<p>I read both diffs against the verifiers. Neither failure came from a broken test or anything outside the agent, so no task was changed after the pilot.</p>
<ul class="plain">
  <li><strong><code>${esc(flakyTasks[0].id)}</code>, run 0.</strong> The docstring for <code>put</code> says to evict the least recently used key and return it. This run returned the evicted value instead (<code>_, evicted = self._items.popitem(last=False)</code>), and the verifier checks for the key. The other two runs returned the key. A plain agent error.</li>
  <li><strong><code>${esc(flakyTasks[1].id)}</code>, run 1.</strong> Codex exited with status 0 after 8.7 seconds and about 42,000 tokens without changing any file. That version of the harness did not save the agent's output, so I do not know why. Three later runs of the same task, outside these results, all passed. rerun-bench now keeps the end of the agent's stdout and stderr with every run, so a failure like this can be diagnosed from the result files.</li>
</ul>

<h2 id="why">Why rerun the same task</h2>
<p>Most coding-agent benchmarks score one attempt per task. If you run an agent once and act on what it did, the number that matters is closer to pass^${k}: the chance that all ${k} runs of a task pass. Here both agents have a pass@${k} of ${pct(m.cc.pass_at_k)}, so every task was solved at least once in ${k} tries. pass^${k} is ${pct(m.cc.pass_hat_k)} for Claude Code and ${pct(m.cx.pass_hat_k)} for Codex CLI, because the two flaky tasks drop out. The flip rate, the chance that two runs of the same task disagree, averaged over tasks, is ${pct(m.cc.flip_rate)} and ${pct(m.cx.flip_rate)}.</p>
<p>Put another way: had I run each task once, Codex CLI could have scored ${nTasks - 2}, ${nTasks - 1} or ${nTasks} out of ${nTasks} on this suite depending on the draw, and a single-run table would have shown only one of those numbers.</p>

<h2 id="limits">What this pilot cannot show</h2>
<ul class="plain">
  <li><strong>A difference between the agents.</strong> With ${k} runs per task, one failure moves a task's pass rate by 33 points. The pass-rate intervals are ${ciWords(m.cc.pass_rate_ci95)} for Claude Code and ${ciWords(m.cx.pass_rate_ci95)} for Codex CLI, and they overlap. The task-bootstrap interval for Codex's mean per-task pass rate is ${ciWords(m.cx.macro_pass_rate_task_bootstrap_ci95)}.</li>
  <li><strong>Anything about large codebases.</strong> These are ${nTasks} small tasks I wrote, mostly in Python, each with a clear verifier.</li>
  <li><strong>Stability over time.</strong> One machine, one morning, one CLI version each. Providers change models and CLIs often.</li>
  <li><strong>Cost.</strong> Claude Code reports a list-price estimate (median ${usd(m.cc.median_cost_usd)} per run), which on a subscription login is quota, not money billed. Codex CLI reports tokens only, so there is no cost comparison.</li>
</ul>

<h2 id="reproduce">Reproduce it</h2>
<p>A free run with a simulated agent shows the whole pipeline and spends nothing:</p>
<div class="cmd"><pre><code>uvx rerun-bench run --agent mock --runs 5</code></pre><button type="button" class="copy" data-copy hidden aria-label="Copy the mock run command">Copy</button></div>
<p>The pilot itself is one command per agent. These start real agent runs and spend your quota; drop <code>--yes</code> to see the run count and a cost estimate first.</p>
<div class="cmd"><pre><code>uvx rerun-bench run --agent claude --runs 3 --yes
uvx rerun-bench run --agent codex --model gpt-6-luna --runs 3 --yes
uvx rerun-bench report results/</code></pre><button type="button" class="copy" data-copy hidden aria-label="Copy the pilot commands">Copy</button></div>
<p>The <a href="${esc(pilotDir)}">pilot directory</a> has every run record and diff, and the <a href="../../methodology/">methodology page</a> defines each metric.</p>

<h2 id="next-run">What I am running next</h2>
<p>A larger run: about 30 tasks with 5 runs each. That gives per-task intervals that mean something, and enough data for the paired comparisons rerun-bench does not do yet: a Fisher exact test per task and a paired task-level bootstrap. It will be published here with its raw run records, like this pilot. To suggest an agent or a task, open an issue on the <a href="${repro}">repository</a>.</p>
</article>`;

  const url = `${SITE_URL}${findingUrl(f)}`;
  return layout({
    path: findingUrl(f),
    title: f.title,
    fullTitle: f.title,
    description: f.description,
    ogType: "article",
    image: {
      url: `${SITE_URL}assets/${f.image.file}`,
      w: f.image.w,
      h: f.image.h,
      alt: `Result card for the ${r.date} pilot: Claude Code ${pct(m.cc.pass_rate)} ${ci(m.cc.pass_rate_ci95)}, pass^${k} ${pct(m.cc.pass_hat_k)}, flip rate ${pct(m.cc.flip_rate)}; Codex CLI ${pct(m.cx.pass_rate)} ${ci(m.cx.pass_rate_ci95)}, pass^${k} ${pct(m.cx.pass_hat_k)}, flip rate ${pct(m.cx.flip_rate)}. The 95% intervals overlap.`,
    },
    head: `<meta property="article:published_time" content="${esc(f.published)}">
<meta property="article:author" content="Abel Yagubyan">
<script type="application/ld+json">${JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Article",
      headline: f.title,
      description: f.description,
      datePublished: f.published,
      author: { "@type": "Person", name: "Abel Yagubyan" },
      image: `${SITE_URL}assets/${f.image.file}`,
      mainEntityOfPage: url,
    }).replace(/</g, "\\u003c")}</script>`,
    body,
  });
}

// Shared <head> metadata and layout for a findings post.
function postLayout(f, alt, body) {
  const url = `${SITE_URL}${findingUrl(f)}`;
  return layout({
    path: findingUrl(f),
    title: f.title,
    fullTitle: f.title,
    description: f.description,
    ogType: "article",
    image: { url: `${SITE_URL}assets/${f.image.file}`, w: f.image.w, h: f.image.h, alt },
    head: `<meta property="article:published_time" content="${esc(f.published)}">
<meta property="article:author" content="Abel Yagubyan">
<script type="application/ld+json">${JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Article",
      headline: f.title,
      description: f.description,
      datePublished: f.published,
      author: { "@type": "Person", name: "Abel Yagubyan" },
      image: `${SITE_URL}assets/${f.image.file}`,
      mainEntityOfPage: url,
    }).replace(/</g, "\\u003c")}</script>`,
    body,
  });
}

// The 4 Codex failures, read from agent_stdout_tail in the source run records.
// `said` is what the final agent message claimed; null when it claimed nothing.
const TEN_RUN_FAILURES = [
  { task: "add-cli-flag", run: 5, wall: "7.0", said: "Added `--words` to wc.py. It counts whitespace-separated tokens and keeps the existing output format" },
  { task: "refactor-extract-helper", run: 7, wall: "9.9", said: "Extracted the existing clamp logic into `clamp_percent(percent)` and updated all three pricing functions to use it." },
  { task: "refactor-extract-helper", run: 9, wall: "8.9", said: "Extracted the repeated clamp into `clamp_percent(percent)` and updated all three pricing functions to use it." },
  { task: "implement-slugify", run: 7, wall: "8.3", said: null },
];

function tenRunPost(f) {
  const r = data.results.find((x) => x.file === f.result);
  if (!r) throw new Error(`finding ${f.slug}: no result set ${f.result}`);
  const es = r.entries.slice().sort(byName);
  const cc = es.find((e) => e.agent === "claude");
  const cx = es.find((e) => e.agent === "codex");
  const m = { cc: cc.metrics, cx: cx.metrics };
  const k = m.cc.k;
  const failsOf = (x) => Object.entries(x.per_task).flatMap(([t, v]) => v.outcomes.map((ok, i) => (ok ? null : `${t}#${i}`)).filter(Boolean));
  const cxFails = failsOf(m.cx).sort();
  const listed = TEN_RUN_FAILURES.map((x) => `${x.task}#${x.run}`).sort();
  // The title and the failure list, checked against the data on every build.
  if (k !== 10 || m.cc.n_tasks !== 10 || failsOf(m.cc).length !== 0 || cxFails.join() !== listed.join() || TEN_RUN_FAILURES.filter((x) => x.said).length !== 3) {
    throw new Error(`finding ${f.slug}: the title or failure list no longer matches ${f.result}`);
  }
  const nTasks = m.cc.n_tasks;
  const nRuns = m.cc.n_runs + m.cx.n_runs;
  const allTasks = Object.keys(m.cc.per_task).sort().map((t) => taskById[t] || { id: t, title: t });
  const flaky = Object.entries(m.cx.per_task).filter(([, t]) => t.outcomes.some(Boolean) && !t.outcomes.every(Boolean));
  const repro = TOOLS.rerunBench;
  const srcDir = r.lab.source_url;
  const pilot = FINDINGS[0];
  // Chance that one run per task passes every task, from the per-task pass rates.
  const oneShotAll = Object.values(m.cx.per_task).reduce((a, t) => a * (t.outcomes.filter(Boolean).length / t.outcomes.length), 1);

  const rows = [
    ["Runs passed", (x) => `${x.passes} of ${x.n_runs}`],
    ["Pass rate, Wilson 95% interval", (x) => `${pct(x.pass_rate)} ${ci(x.pass_rate_ci95)}`],
    [`pass^${k}: all ${k} runs pass`, (x) => pct(x.pass_hat_k)],
    ["Flip rate: two runs of a task disagree", (x) => pct(x.flip_rate)],
    ["Tasks with both a pass and a fail", (x) => `${Math.round(x.flaky_task_fraction * x.n_tasks)} of ${x.n_tasks}`],
    ["Median wall time per run", (x) => `${x.wall_time_median_s.toFixed(1)} s`],
  ];
  const table = `<div class="tablewrap"><table class="data metrics post-table">
<caption class="sr-only">Headline numbers for the 10-run set</caption>
<thead><tr><th scope="col">Metric</th><th scope="col" class="num">Claude Code</th><th scope="col" class="num">Codex</th></tr></thead>
<tbody>${rows.map(([name, fn]) => `<tr><th scope="row">${esc(name)}</th><td class="num">${esc(fn(m.cc))}</td><td class="num">${esc(fn(m.cx))}</td></tr>`).join("")}</tbody></table></div>`;
  const mdCode = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
  const failTable = `<div class="tablewrap"><table class="data post-table">
<caption class="sr-only">The four Codex CLI failures</caption>
<thead><tr><th scope="col">Task</th><th scope="col" class="num">Run</th><th scope="col" class="num">Time</th><th scope="col">What its final message said</th></tr></thead>
<tbody>${TEN_RUN_FAILURES.map((x) => `<tr><th scope="row"><code>${esc(x.task)}</code></th><td class="num">${x.run}</td><td class="num">${x.wall} s</td><td>${x.said ? `&ldquo;${mdCode(x.said)}&rdquo;` : "That it had read the spec and would now implement it. It then exited."}</td></tr>`).join("")}</tbody></table></div>`;

  const body = `<article class="post" aria-labelledby="post-title">
<header class="page-head post-head">
  <p class="eyebrow"><span class="mono">${esc(f.published)}</span> <a href="../">Findings</a></p>
  <h1 id="post-title">${esc(f.title)}</h1>
  <p class="byline small">By Abel Yagubyan. Data: <a href="../../results/#r-${r.date}-${r.label}">the ${esc(r.date)} result set</a> (<a href="../../data/results/${esc(r.file)}">raw JSON</a>, <a href="${esc(srcDir)}">run records and diffs</a>).</p>
</header>

<p class="lede">I gave Claude Code and Codex CLI the same ${nTasks} small coding tasks and ran each task ${k} times per agent, ${nRuns} runs in all. Claude Code passed all ${m.cc.n_runs}. Codex CLI passed ${m.cx.passes}, and its ${m.cx.n_runs - m.cx.passes} failures were all the same kind: it read the file, changed nothing, and exited cleanly within 10 seconds. In 3 of those 4 runs its last message said it had made the change. The overall pass rates are too close to call. How Codex failed is the part worth reading.</p>

<h2 id="setup">What I ran</h2>
<p>This is the follow-up to <a href="../${pilot.slug}/">a 60-run pilot</a>, with ${k} runs per task instead of 3, using <a href="${repro}">rerun-bench</a>, an evaluation tool I build. Each run starts from a fresh copy of the task's files, drives the agent's CLI headlessly, and is scored only by the task's own verifier script. What the agent says about its work is recorded but never scored.</p>
<ul class="plain">
  <li>Claude Code ${esc(cc.cli_version.replace(/ \(Claude Code\)$/, ""))}, pinned to <code>${esc(cc.model)}</code>.</li>
  <li>Codex CLI ${esc(cx.cli_version.replace(/^codex-cli /, ""))} with <code>${esc(cx.model)}</code>, the model that version picks when none is configured.</li>
  <li>The same ${nTasks} tasks as the pilot: fixing the bug behind a failing test, implementing a function from its docstring, renaming across a package, extracting a helper, and so on.</li>
  <li>One Mac (${esc(r.lab.machine)}). Codex ran on the afternoon of ${esc(r.date)} and Claude Code that evening, US Eastern time. Harness: rerun-bench ${esc(r.rerun_bench_version)} at commit ${esc(r.lab.harness_commit)}.</li>
</ul>

<h2 id="numbers">The numbers</h2>
${intervalChart({
  id: "post-ci",
  title: "Pass rate with Wilson 95% interval",
  desc: "The dot is the share of runs that passed; the bar is the 95% interval. The bars overlap.",
  rows: es.map((e) => ({
    label: entryLabel(e),
    sub: e.model,
    est: e.metrics.pass_rate,
    lo: e.metrics.pass_rate_ci95[0],
    hi: e.metrics.pass_rate_ci95[1],
    tipNote: `${e.metrics.passes} of ${e.metrics.n_runs} runs passed`,
  })),
})}
${table}
${consistencyGrid({
  id: "post-grid",
  title: "Every run, by task",
  desc: `Each mark is one run, in the order they ran. Codex CLI has a fail on ${flaky.length} tasks.`,
  tasks: allTasks,
  agents: es.map((e) => ({
    label: entryLabel(e),
    runs: k,
    perTask: Object.fromEntries(Object.entries(e.metrics.per_task).map(([t, v]) => [t, v.outcomes])),
  })),
})}

<h2 id="failures">How Codex failed</h2>
<p>The ${TEN_RUN_FAILURES.length} failures look almost identical. Codex listed or printed the relevant file, issued no edit, and exited with status 0 after 7 to 10 seconds, writing 115 to 205 output tokens against a median of ${Math.round(m.cx.output_tokens_median)} across all its runs. The recorded diffs are empty and the verifiers failed on the unchanged code. These weren't hard tasks for it. It passed each of them on most of its other runs.</p>
${failTable}
<p>When an agent tells you it failed, you just try again. When it tells you it succeeded and didn't, you usually find out later, when something else breaks. Three of these four runs would have looked finished to me if I hadn't been checking the files.</p>
<p>The pilot had one unexplained Codex failure, on <code>refactor-extract-helper</code>: exit 0 after 8.7 seconds, no file changed. That harness version did not keep the agent's output, so I could not say why. In hindsight it looks like the same thing.</p>

<h2 id="why">Why ${k} runs changed the picture</h2>
<p>With 3 runs per task, the pilot had two Codex failures that looked unrelated. With ${k}, the pattern is visible: ${pct(m.cx.pass_hat_k)} of tasks passed all ${k} times for Codex CLI, against ${pct(m.cc.pass_hat_k)} for Claude Code, and the flip rate was ${pct(m.cx.flip_rate)} against ${pct(m.cc.flip_rate)}. Had I run each task once, Codex CLI would have scored ${nTasks} out of ${nTasks} about ${pct(oneShotAll)} of the time on these per-task rates, and this behavior would not have shown up at all.</p>

<h2 id="default-model">A side result: the default model changed</h2>
<p>In the pilot, Claude Code with no model flag reported <code>claude-opus-5-5</code>. Three days later, on the same account and even with the pilot's CLI version, it reported <code>claude-opus-4-8</code>. I do not know why. I pinned the model for the comparison above, and also ran ${k} runs per task on the new default: it passed all 100, at a median ${usd(0.1312)} per run against ${usd(m.cc.median_cost_usd)} for the pinned model. Those runs are in the <a href="${esc(srcDir)}">source directory</a>.</p>

<h2 id="limits">What this cannot show</h2>
<ul class="plain">
  <li><strong>A difference in overall pass rate.</strong> The intervals are ${ciWords(m.cc.pass_rate_ci95)} for Claude Code and ${ciWords(m.cx.pass_rate_ci95)} for Codex CLI, and they overlap.</li>
  <li><strong>How often this happens in real work.</strong> These are ${nTasks} small tasks I wrote, mostly in Python. Four runs out of 100 is a rate on this suite, not on your codebase.</li>
  <li><strong>Why it happens.</strong> The run records show what Codex did, not why it stopped. One CLI version, one model, one day.</li>
  <li><strong>Cost.</strong> Claude Code reports a list-price estimate, which on a subscription is quota, not money billed. Codex CLI reports tokens only.</li>
</ul>

<h2 id="reproduce">Reproduce it</h2>
<p>A free run with a simulated agent shows the whole pipeline and spends nothing:</p>
<div class="cmd"><pre><code>uvx rerun-bench run --agent mock --runs 5</code></pre><button type="button" class="copy" data-copy hidden aria-label="Copy the mock run command">Copy</button></div>
<p>This result set is one command per agent. They start real agent runs and spend your quota; drop <code>--yes</code> to see the run count and a cost estimate first.</p>
<div class="cmd"><pre><code>uvx rerun-bench run --agent claude --model claude-opus-5-5 --runs 10 --yes
uvx rerun-bench run --agent codex --model gpt-6-luna --runs 10 --yes
uvx rerun-bench report results/</code></pre><button type="button" class="copy" data-copy hidden aria-label="Copy the commands for this result set">Copy</button></div>
<p>Every run record, including the agent's final output, is in the <a href="${esc(srcDir)}">source directory</a>. The <a href="../../methodology/">methodology page</a> defines each metric.</p>

<h2 id="next-run">What I am running next</h2>
<p>A check for this exact failure: flag any run where the agent ends with a claim of having edited files while the workspace is unchanged, and report it as its own metric. Then more tasks, so the per-task numbers mean something. To suggest an agent or a task, open an issue on the <a href="${repro}">repository</a>.</p>
</article>`;

  return postLayout(
    f,
    `Result card for the ${r.date} result set: Claude Code ${pct(m.cc.pass_rate)} ${ci(m.cc.pass_rate_ci95)}, pass^${k} ${pct(m.cc.pass_hat_k)}, flip rate ${pct(m.cc.flip_rate)}; Codex CLI ${pct(m.cx.pass_rate)} ${ci(m.cx.pass_rate_ci95)}, pass^${k} ${pct(m.cx.pass_hat_k)}, flip rate ${pct(m.cx.flip_rate)}. The 95% intervals overlap.`,
    body,
  );
}

function findingsIndex() {
  const items = FINDINGS.slice()
    .sort((a, b) => b.published.localeCompare(a.published))
    .map((f) => `<li><span class="mono small">${esc(f.published)}</span> <a href="${f.slug}/">${esc(f.title)}</a><br><span class="small">${esc(f.description)}</span></li>`)
    .join("");
  return layout({
    path: "findings/",
    title: "Findings",
    description: "Write-ups of result sets from open agent lab: what was run, what it shows, and what it cannot show.",
    body: `<div class="page-head">
  <p class="eyebrow"><span class="mono">06</span> Findings</p>
  <h1>Findings</h1>
  <p class="lede">Each finding is a short write-up of one result set: what was run, the numbers with their intervals, and what the data cannot show.</p>
</div>
<ul class="plain findings-list">${items}</ul>`,
  });
}

function notFoundPage() {
  return layout({
    path: "404",
    absolute: true,
    title: "Not found",
    description: "Page not found.",
    body: `<div class="page-head"><p class="eyebrow"><span class="mono">404</span></p><h1>No page here.</h1><p class="lede"><a href="${BASE}">Back to the home page</a>.</p></div>`,
  });
}

// ---------------------------------------------------------------- write

rmSync(OUT, { recursive: true, force: true });
const write = (rel, content) => {
  const p = join(OUT, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, content);
};

write("index.html", homePage());
write("results/index.html", resultsPage());
write("methodology/index.html", methodologyPage());
write("regressions/index.html", regressionsPage());
write("launches/index.html", launchesPage());
write("404.html", notFoundPage());
write("findings/index.html", findingsIndex());
for (const f of FINDINGS) write(`${findingUrl(f)}index.html`, f.render(f));
write(".nojekyll", "");

const copyDir = (from, to) => {
  mkdirSync(to, { recursive: true });
  for (const f of readdirSync(from, { withFileTypes: true })) {
    if (f.name.startsWith(".")) continue;
    if (f.isDirectory()) copyDir(join(from, f.name), join(to, f.name));
    else copyFileSync(join(from, f.name), join(to, f.name));
  }
};
copyDir(join(root, "src"), join(OUT, "assets"));
if (existsSync(join(root, "data"))) copyDir(join(root, "data"), join(OUT, "data"));

console.log(`built ${OUT.replace(root + "/", "")}: ${7 + FINDINGS.length} pages, ${data.results.length} result set(s)`);
