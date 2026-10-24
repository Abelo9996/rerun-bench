#!/usr/bin/env node
// Renders the 1280x640 social preview image from the latest result set with
// headless Chrome. Writes src/social-preview.png (served as
// assets/social-preview.png) and a copy at docs/social-preview.png for the
// repository's social preview setting.
// Usage: node scripts/social.mjs [--chrome /path/to/chrome] [--html-only]

import { mkdtempSync, writeFileSync, copyFileSync, existsSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { loadAll } from "./lib/data.mjs";
import { esc, ciWords } from "./lib/charts.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : null;
};
const CHROME_PATHS = [
  arg("--chrome"),
  process.env.CHROME,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

const { errors, data } = loadAll(root);
if (errors.length) {
  for (const e of errors) console.error(`error: ${e}`);
  process.exit(1);
}
const latest = data.results[0];
const agentName = (id) => data.agents.find((a) => a.id === id)?.name || id;

let panel = "";
if (latest) {
  const es = latest.entries.slice().sort((a, b) => agentName(a.agent).localeCompare(agentName(b.agent)));
  const tasks = [...new Set(es.flatMap((e) => Object.keys(e.metrics.per_task)))].sort();
  const runs = Math.max(...es.flatMap((e) => Object.values(e.metrics.per_task).map((t) => t.n)));
  const head = es.map((e) => `<th colspan="${runs}">${esc(agentName(e.agent))}</th>`).join('<td class="gap"></td>');
  const rows = tasks
    .map(
      (t) =>
        `<tr><th class="task">${esc(t)}</th>${es
          .map((e) =>
            Array.from({ length: runs }, (_, i) => {
              const o = e.metrics.per_task[t]?.outcomes?.[i];
              if (o === undefined) return `<td><span class="c na"></span></td>`;
              return `<td><span class="c ${o ? "pass" : "fail"}">${o ? "&#10003;" : "&#10005;"}</span></td>`;
            }).join(""),
          )
          .join('<td class="gap"></td>')}</tr>`,
    )
    .join("");
  const tallies = es
    .map(
      (e) =>
        `<div><span class="lab">${esc(agentName(e.agent))}</span><span class="num">${e.metrics.passes}/${e.metrics.n_runs}</span><span class="ci">passed<br>95% interval: ${ciWords(e.metrics.pass_rate_ci95).replace(/% to /, " to ")}</span></div>`,
    )
    .join("");
  panel = `<div class="panel">
  <div class="bar"><span class="light"></span>rerun-bench ${esc(latest.rerun_bench_version)} &middot; ${esc(latest.date)}${latest.lab.pilot ? " pilot" : ""}</div>
  <table><thead><tr><td></td>${head}</tr></thead><tbody>${rows}</tbody></table>
  <div class="tallies">${tallies}</div>
</div>`;
}

const html = `<!doctype html>
<html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
html,body{margin:0;width:1280px;height:640px;overflow:hidden}
body{background:#0c1110;color:#e7eeeb;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;position:relative}
.mono,.bar,.task,.ci,.lab,.url,.eyebrow{font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
.ruler{position:absolute;left:0;right:0;top:0;height:18px;background-image:repeating-linear-gradient(90deg,#b7c3be 0 2px,transparent 2px 128px),repeating-linear-gradient(90deg,#3d4a46 0 1px,transparent 1px 16px);background-size:100% 18px,100% 9px;background-position:0 0,0 0;background-repeat:no-repeat;border-bottom:1px solid #2c3734}
.left{position:absolute;left:72px;top:92px;width:560px}
.brand{display:flex;align-items:center;gap:14px;font-weight:700;font-size:28px;letter-spacing:-0.01em}
.brand svg rect{fill:#e7eeeb}.brand svg .hi{fill:#5fd0ad}
h1{font-size:68px;line-height:1.02;letter-spacing:-0.035em;font-weight:780;margin:40px 0 24px}
p{font-size:25px;line-height:1.4;color:#b7c3be;margin:0;max-width:520px}
.hl{background:#cdea45;color:#182000;padding:0 8px;border-radius:4px;font-weight:650}
.url{position:absolute;left:72px;bottom:52px;font-size:20px;color:#91a09a}
.url b{color:#5fd0ad;font-weight:500}
.panel{position:absolute;right:64px;top:70px;width:500px;background:#151b1a;border:1px solid #2c3734;border-radius:8px;padding-bottom:16px}
.bar{display:flex;align-items:center;gap:10px;font-size:15px;color:#91a09a;padding:12px 18px;border-bottom:1px solid #2c3734}
.light{width:10px;height:10px;border-radius:50%;background:#5fd0ad;box-shadow:0 0 0 4px #15302a}
table{border-collapse:separate;border-spacing:4px;margin:10px 14px 0}
thead th{font-size:15px;font-weight:650;text-align:left;border-bottom:1px solid #2c3734;padding:0 0 4px 2px}
td{padding:0;text-align:center}
td.gap{width:12px}
.task{font-size:13.5px;font-weight:400;color:#b7c3be;text-align:left;padding-right:14px;white-space:nowrap}
.c{display:inline-flex;width:26px;height:26px;border-radius:4px;align-items:center;justify-content:center;font-size:15px;font-weight:700}
.pass{background:#173a1d;color:#7fdc7f}.fail{background:#d03b3b;color:#fff}.na{border:1px dashed #3d4a46}
.tallies{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:12px 18px 0;padding-top:12px;border-top:1px solid #242e2b}
.lab{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#91a09a}
.num{font-size:30px;font-weight:750;letter-spacing:-0.01em}
.ci{display:block;white-space:nowrap;font-size:14px;color:#91a09a}
</style></head><body>
<div class="ruler"></div>
<div class="left">
  <div class="brand"><svg width="42" height="30" viewBox="0 0 28 20"><rect x="1" y="6" width="4" height="13" rx="1"/><rect x="8" y="2" width="4" height="17" rx="1"/><rect x="15" y="8" width="4" height="11" rx="1"/><rect x="22" y="2" width="4" height="17" rx="1" class="hi"/></svg>open agent lab</div>
  <h1>Coding agents, measured more than once.</h1>
  <p>Same tasks, <span class="hl">many runs</span>, intervals shown. Reproducible evaluation of Claude Code, Codex and other coding agents.</p>
</div>
<div class="url"><b>abelo9996.github.io</b>/rerun-bench</div>
${panel}
</body></html>`;

const dir = mkdtempSync(join(tmpdir(), "oal-social-"));
const htmlPath = join(dir, "card.html");
writeFileSync(htmlPath, html);
if (process.argv.includes("--html-only")) {
  console.log(htmlPath);
  process.exit(0);
}
const chrome = CHROME_PATHS.find((p) => existsSync(p));
if (!chrome) {
  console.error("Chrome not found. Pass --chrome <path> or set CHROME.");
  process.exit(1);
}
const shot = join(dir, "card.png");
execFileSync(
  chrome,
  ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=1280,640", `--screenshot=${shot}`, `file://${htmlPath}`],
  { stdio: "ignore" },
);
const out = join(root, "src", "social-preview.png");
copyFileSync(shot, out);
copyFileSync(shot, join(root, "docs", "social-preview.png"));
rmSync(dir, { recursive: true, force: true });
console.log("wrote src/social-preview.png and docs/social-preview.png");
