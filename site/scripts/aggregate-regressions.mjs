#!/usr/bin/env node
// Reads open issues labeled regression-report, validates the nerf-watch JSON
// in each, and writes the aggregate to data/regressions.json. The file is
// only rewritten when its content changes.
//
// Usage:
//   GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo node scripts/aggregate-regressions.mjs
//   node scripts/aggregate-regressions.mjs --issues issues.json [--out file]   (offline, for testing)
//
// Issue content is untrusted. It is parsed as JSON and validated by
// scripts/lib/regressions.mjs; nothing from it is executed, and the log
// prints issue numbers and rejection reasons only.

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { LABEL, processIssues, serialize } from "./lib/regressions.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const MAX_PAGES = 10; // 1,000 issues

function arg(name) {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : undefined;
}

const target = arg("--out") || join(root, "data", "regressions.json");

async function fetchIssues(repo, token) {
  const out = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const url = `https://api.github.com/repos/${repo}/issues?state=open&labels=${encodeURIComponent(LABEL)}&per_page=100&page=${page}`;
    const res = await fetch(url, {
      headers: {
        accept: "application/vnd.github+json",
        "x-github-api-version": "2022-11-28",
        "user-agent": "open-agent-lab-regression-aggregator",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!res.ok) throw new Error(`GitHub API ${res.status} ${res.statusText} for page ${page}`);
    const batch = await res.json();
    if (!Array.isArray(batch)) throw new Error("GitHub API returned something other than a list");
    out.push(...batch);
    if (batch.length < 100) break;
  }
  return out;
}

async function main() {
  const repo = process.env.GITHUB_REPOSITORY || "Abelo9996/open-agent-lab";
  if (!/^[A-Za-z0-9-]+\/[A-Za-z0-9._-]+$/.test(repo)) throw new Error("GITHUB_REPOSITORY is not owner/repo");
  const repoUrl = `https://github.com/${repo}`;
  const file = arg("--issues");
  const issues = file ? JSON.parse(readFileSync(file, "utf8")) : await fetchIssues(repo, process.env.GITHUB_TOKEN);

  const { aggregates, accepted, rejected } = processIssues(issues, { repoUrl });
  console.log(`issues read: ${issues.length}; accepted: ${accepted.length}; rejected: ${rejected.length}; aggregate rows: ${aggregates.length}`);
  if (accepted.length) console.log(`accepted: ${accepted.map((n) => `#${n}`).join(", ")}`);
  for (const r of rejected) console.log(`rejected #${r.number ?? "?"}: ${r.reason}`);

  const before = existsSync(target) ? readFileSync(target, "utf8") : "";
  let existing = {};
  try {
    existing = before ? JSON.parse(before) : {};
  } catch {
    throw new Error("data/regressions.json is not valid JSON; fix it by hand first");
  }
  const after = serialize(existing, aggregates);
  if (after === before) {
    console.log("data/regressions.json unchanged");
    return;
  }
  writeFileSync(target, after);
  console.log("data/regressions.json updated");
}

main().catch((e) => {
  console.error(`error: ${e.message}`);
  process.exit(1);
});
