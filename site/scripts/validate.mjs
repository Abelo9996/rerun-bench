#!/usr/bin/env node
// Validates every file under data/. Exits 1 on any error.
// Usage: node scripts/validate.mjs

import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { loadAll } from "./lib/data.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const { errors, warnings, data } = loadAll(root);

for (const w of warnings) console.warn(`warning: ${w}`);
if (errors.length) {
  for (const e of errors) console.error(`error: ${e}`);
  console.error(`\n${errors.length} error(s). See CONTRIBUTING.md for the expected format.`);
  process.exit(1);
}
console.log(
  `ok: ${data.results.length} result file(s), ${data.agents.length} agents, ${data.tasks.tasks.length} tasks, ` +
    `${data.regressions.length} reviewed regression report(s), ${data.regressionAggregates.length} aggregate regression row(s), ` +
    `${data.launches.length} launch(es)`,
);
