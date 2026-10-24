// Builds the site into a temporary folder and checks what a first-time visitor
// relies on: working internal links and anchors, install commands that match
// the published packages, social preview tags, plain-language summaries next
// to the metrics, and keyboard and screen reader basics. Run with `npm test`.

import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, rmSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outRel = `.test-site-${process.pid}`;
const out = join(root, outRel);
const SITE_URL = "https://abelo9996.github.io/rerun-bench/";
const POST = "findings/2026-10-rerun-pilot/index.html";
const POST_TITLE = "Same task, 3 runs: Codex passed and failed on 2 of 10 tasks, Claude Code on 0";
const POST2 = "findings/2026-10-rerun-10x/index.html";
const POST2_TITLE = "Same task, 10 runs: Codex CLI reported edits it never made in 3 of 100 runs";
const PAGES = ["index.html", "results/index.html", "methodology/index.html", "regressions/index.html", "launches/index.html", "404.html", "findings/index.html", POST, POST2];
const html = {};

before(() => {
  execFileSync(process.execPath, [join(root, "scripts", "build.mjs"), "--out", outRel], { cwd: root, stdio: "pipe" });
  for (const p of PAGES) html[p] = readFileSync(join(out, p), "utf8");
});
after(() => rmSync(out, { recursive: true, force: true }));

const ids = (s) => new Set([...s.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));

test("every internal link and anchor resolves to a built file and element", () => {
  const problems = [];
  for (const p of PAGES) {
    if (p === "404.html") continue; // uses absolute /rerun-bench/ paths, checked below
    const base = new URL(p, "https://x.test/");
    for (const m of html[p].matchAll(/\s(?:href|src|data-gif)="([^"]+)"/g)) {
      const ref = m[1].replace(/&amp;/g, "&");
      if (/^(https?:|mailto:)/.test(ref)) continue;
      const u = new URL(ref, base);
      let file = decodeURIComponent(u.pathname.slice(1));
      if (file === "" || file.endsWith("/")) file += "index.html";
      const abs = join(out, file);
      if (!existsSync(abs) || statSync(abs).isDirectory()) {
        problems.push(`${p}: ${ref} (no ${file})`);
        continue;
      }
      const hash = u.hash.slice(1);
      if (hash && file.endsWith(".html") && !ids(readFileSync(abs, "utf8")).has(decodeURIComponent(hash))) {
        problems.push(`${p}: ${ref} (no #${hash})`);
      }
    }
  }
  assert.deepEqual(problems, []);
});

test("the 404 page links back with absolute paths", () => {
  assert.match(html["404.html"], /href="\/rerun-bench\/"/);
  assert.match(html["404.html"], /href="\/rerun-bench\/assets\/style\.css"/);
});

test("tool install commands match the published packages", () => {
  const cmds = [...html["index.html"].matchAll(/<div class="cmd"><pre><code>([^<]+)<\/code>/g)].map((m) => m[1].replace(/&amp;/g, "&"));
  assert.deepEqual(cmds, [
    "npx nerf-watch check",
    "uvx rerun-bench run --agent mock",
    "npx @abelo9996/snap-back wrap -- codex",
    "npm install -g @abelo9996/agent-fence",
    "git clone https://github.com/Abelo9996/launch-day-kit",
  ]);
  for (const p of PAGES) {
    assert.doesNotMatch(html[p], /git\+https:\/\/github\.com\/Abelo9996\/rerun-bench/, `${p} still installs rerun-bench from git`);
    // Unscoped snap-back and agent-fence are not published on npm.
    assert.doesNotMatch(html[p], /npm install -g (snap-back|agent-fence)\b|npx (snap-back|agent-fence)\b/, `${p} uses an unpublished package name`);
  }
  assert.match(html["methodology/index.html"], /uv tool install rerun-bench\n/);
});

test("packaged tools show their Homebrew tap install line", () => {
  const brews = [...html["index.html"].matchAll(/<p class="cmd-brew small">Homebrew \(macOS and Linux\): <code>([^<]+)<\/code><\/p>/g)].map((m) => m[1]);
  assert.deepEqual(brews, [
    "brew install abelo9996/tap/nerf-watch",
    "brew install abelo9996/tap/rerun-bench",
    "brew install abelo9996/tap/snap-back",
    "brew install abelo9996/tap/agent-fence",
  ]);
});

test("packaged tools show the plugin install line for the open-agent-lab marketplace", () => {
  const lines = [...html["index.html"].matchAll(/<p class="cmd-plugin small">Claude Code plugin: <code>\/plugin install ([^<]+)<\/code> after <code>\/plugin marketplace add ([^<]+)<\/code>\. Codex: <code>codex plugin add ([^<]+)<\/code> from the same marketplace\.<\/p>/g)];
  assert.deepEqual(
    lines.map((m) => m[1]),
    ["nerf-watch@open-agent-lab", "rerun-bench@open-agent-lab", "snap-back@open-agent-lab", "agent-fence@open-agent-lab"],
  );
  for (const m of lines) {
    assert.equal(m[2], "Abelo9996/open-agent-lab");
    assert.equal(m[3], m[1]);
  }
});

test("every tool section names a next step after its first command", () => {
  const thens = html["index.html"].match(/<p class="cmd-then small">/g) || [];
  assert.equal(thens.length, 5);
});

test("every page has Open Graph and Twitter tags with absolute URLs", () => {
  for (const p of PAGES) {
    for (const name of ["og:title", "og:description", "og:url", "og:image", "twitter:card", "twitter:title", "twitter:description", "twitter:image"]) {
      const m = html[p].match(new RegExp(`(?:property|name)="${name}" content="([^"]*)"`));
      assert.ok(m && m[1], `${p} is missing ${name}`);
      if (/url|image/.test(name)) assert.ok(m[1].startsWith(SITE_URL), `${p} ${name} is not absolute: ${m[1]}`);
    }
  }
  assert.ok(existsSync(join(out, "assets", "social-preview.png")));
});

test("headline numbers come with a plain-language reading", () => {
  // The home page shows the latest result set; the results page shows every set.
  const latest = /<strong>In plain words:<\/strong> Claude Code passed 100 of 100 runs and Codex CLI passed 96 of 100 runs: 10 tasks, each run 10 times/;
  for (const p of ["index.html", "results/index.html"]) assert.match(html[p], latest);
  assert.match(html["results/index.html"], /<strong>In plain words:<\/strong> Claude Code passed 30 of 30 runs and Codex CLI passed 28 of 30 runs: 10 tasks, each run 3 times/);
  assert.match(html["results/index.html"], /This is a pilot/);
  assert.doesNotMatch(html["index.html"], /This is a pilot/);
  const home = html["index.html"];
  assert.match(home, /<dl class="key">/);
  for (const term of ["pass rate [low, high]", "pass^10", "flip rate", "median tokens"]) assert.ok(home.includes(`<dt>${term}</dt>`), term);
  // The hero interval reads as a range, not as a second pass rate.
  assert.match(home, /95% interval: 96% to 100%/);
  assert.doesNotMatch(home, /class="hg-ci">95% \[/);
});

test("every page ends with something to do", () => {
  assert.match(html["results/index.html"], /id="next"/);
  assert.match(html["launches/index.html"], /id="l-follow"/);
  assert.match(html["regressions/index.html"], /Report a suspected regression/);
  assert.match(html["methodology/index.html"], /id="m-repro"/);
});

test("each chart and pass/fail grid is a single tab stop", () => {
  for (const [page, min] of [["results/index.html", 5], [POST, 2]]) {
    const r = html[page];
    const groups = r.split(/(?=<div class="cbody" role="list" data-rove>|<table class="grid-table" data-rove>)/).slice(1);
    assert.ok(groups.length >= min, `${page}: expected charts and a grid, found ${groups.length}`);
    for (const g of groups) {
      const end = g.indexOf(g.startsWith("<table") ? "</table>" : '<div class="crow crow-axis"');
      const body = g.slice(0, end);
      const roving = body.match(/tabindex="-?\d+"/g) || [];
      // Exactly one tab stop; every other roving item is removed from the tab order.
      // A single-item group (e.g. a one-agent chart) has the one stop and no siblings.
      assert.equal(roving.filter((t) => t === 'tabindex="0"').length, 1, body.slice(0, 80));
      assert.ok(roving.every((t) => t === 'tabindex="0"' || t === 'tabindex="-1"'), body.slice(0, 80));
    }
  }
});

test("no aria-label on elements without a role, and every image has alt text", () => {
  for (const p of PAGES) {
    assert.doesNotMatch(html[p], /<span(?![^>]*\brole=)[^>]*\saria-label=/, `${p} has aria-label on a plain span`);
    for (const m of html[p].matchAll(/<img\b[^>]*>/g)) assert.match(m[0], /\salt="[^"]+"/, `${p}: ${m[0]}`);
  }
});

test("built pages contain no long dashes", () => {
  for (const p of PAGES) assert.doesNotMatch(html[p], /[–—]/, p);
});

test("the findings post stands on its own: title, canonical URL and a dedicated share card", () => {
  const p = html[POST];
  const url = `${SITE_URL}findings/2026-10-rerun-pilot/`;
  assert.ok(p.includes(`<title>${POST_TITLE}</title>`), "title is the post title alone, without the site suffix");
  assert.ok(p.includes(`<h1 id="post-title">${POST_TITLE}</h1>`));
  assert.ok(POST_TITLE.length <= 80, "Hacker News titles are capped at 80 characters");
  assert.ok(p.includes(`<link rel="canonical" href="${url}">`));
  assert.ok(p.includes(`<meta property="og:url" content="${url}">`));
  assert.ok(p.includes('<meta property="og:type" content="article">'));
  const img = `${SITE_URL}assets/findings/2026-10-rerun-pilot.png`;
  assert.ok(p.includes(`<meta property="og:image" content="${img}">`));
  assert.ok(p.includes(`<meta name="twitter:image" content="${img}">`));
  assert.ok(p.includes('<meta property="og:image:width" content="1200">'));
  assert.ok(p.includes('<meta property="og:image:height" content="630">'));
  assert.ok(p.includes('<meta name="twitter:card" content="summary_large_image">'));
  // The card on disk really is 1200x630 (PNG IHDR width and height).
  const png = readFileSync(join(out, "assets", "findings", "2026-10-rerun-pilot.png"));
  assert.equal(png.readUInt32BE(16), 1200);
  assert.equal(png.readUInt32BE(20), 630);
  const ld = JSON.parse(p.match(/<script type="application\/ld\+json">([^<]+)<\/script>/)[1]);
  assert.equal(ld.headline, POST_TITLE);
  assert.equal(ld.mainEntityOfPage, url);
});

test("the findings post is 600 to 900 words of prose and says what the pilot cannot show", () => {
  let a = html[POST].slice(html[POST].indexOf("<article"), html[POST].indexOf("</article>"));
  for (const re of [/<figure[\s\S]*?<\/figure>/g, /<div class="tablewrap">[\s\S]*?<\/div>/g, /<div class="cmd">[\s\S]*?<\/div>/g]) a = a.replace(re, "");
  const words = a.replace(/<[^>]+>/g, " ").split(/\s+/).filter(Boolean).length;
  assert.ok(words >= 600 && words <= 900, `${words} words`);
  const p = html[POST];
  for (const id of ["setup", "numbers", "failures", "why", "limits", "reproduce", "next-run"]) assert.ok(ids(p).has(id), id);
  assert.match(p, /Claude Code 2\.1\.288/);
  assert.match(p, /Codex CLI 0\.160\.0/);
  assert.match(p, /<code>claude-opus-5-5<\/code>/);
  assert.match(p, /<code>gpt-6-luna<\/code>/);
  assert.match(p, /89% to 100% for Claude Code and 79% to 98% for Codex CLI, and they overlap/);
  assert.match(p, /pass\^3 is 100% for Claude Code and 80% for Codex CLI/);
  assert.match(p, /<code>implement-lru-cache<\/code>, run 0/);
  assert.match(p, /<code>refactor-extract-helper<\/code>, run 1/);
  assert.match(p, /uvx rerun-bench run --agent mock --runs 5/);
  assert.match(p, /about 30 tasks with 5 runs each/);
  assert.doesNotMatch(p, /\b(best|winner|beats|groundbreaking|revolutionary)\b/i);
});

test("each findings post is linked from the results page and the findings index, the latest from the home page", () => {
  assert.match(html["index.html"], /href="findings\/2026-10-rerun-10x\/"/);
  for (const slug of ["2026-10-rerun-pilot", "2026-10-rerun-10x"]) {
    assert.match(html["results/index.html"], new RegExp(`href="\\.\\./findings/${slug}/"`));
    assert.match(html["findings/index.html"], new RegExp(`href="${slug}/"`));
  }
});

test("the 10-run post stands on its own: title, canonical URL and a dedicated share card", () => {
  const p = html[POST2];
  const url = `${SITE_URL}findings/2026-10-rerun-10x/`;
  assert.ok(p.includes(`<title>${POST2_TITLE}</title>`));
  assert.ok(p.includes(`<h1 id="post-title">${POST2_TITLE}</h1>`));
  assert.ok(POST2_TITLE.length <= 80, "Hacker News titles are capped at 80 characters");
  assert.ok(p.includes(`<link rel="canonical" href="${url}">`));
  const img = `${SITE_URL}assets/findings/2026-10-rerun-10x.png`;
  assert.ok(p.includes(`<meta property="og:image" content="${img}">`));
  const png = readFileSync(join(out, "assets", "findings", "2026-10-rerun-10x.png"));
  assert.equal(png.readUInt32BE(16), 1200);
  assert.equal(png.readUInt32BE(20), 630);
  const ld = JSON.parse(p.match(/<script type="application\/ld\+json">([^<]+)<\/script>/)[1]);
  assert.equal(ld.headline, POST2_TITLE);
  assert.equal(ld.mainEntityOfPage, url);
});

test("the 10-run post is 600 to 950 words, names every failure and says what it cannot show", () => {
  let a = html[POST2].slice(html[POST2].indexOf("<article"), html[POST2].indexOf("</article>"));
  for (const re of [/<figure[\s\S]*?<\/figure>/g, /<div class="tablewrap">[\s\S]*?<\/div>/g, /<div class="cmd">[\s\S]*?<\/div>/g]) a = a.replace(re, "");
  const words = a.replace(/<[^>]+>/g, " ").split(/\s+/).filter(Boolean).length;
  assert.ok(words >= 600 && words <= 950, `${words} words`);
  const p = html[POST2];
  for (const id of ["setup", "numbers", "failures", "why", "default-model", "limits", "reproduce", "next-run"]) assert.ok(ids(p).has(id), id);
  assert.match(p, /Claude Code 2\.1\.292, pinned to <code>claude-opus-5-5<\/code>/);
  assert.match(p, /Codex CLI 0\.160\.0 with <code>gpt-6-luna<\/code>/);
  assert.match(p, /96% to 100% for Claude Code and 90% to 98% for Codex CLI, and they overlap/);
  for (const [task, run] of [["add-cli-flag", 5], ["refactor-extract-helper", 7], ["refactor-extract-helper", 9], ["implement-slugify", 7]]) {
    assert.match(p, new RegExp(`<code>${task}</code></th><td class="num">${run}</td>`));
  }
  assert.match(p, /about 65% of the time/);
  assert.match(p, /<code>claude-opus-4-8<\/code>/);
  assert.match(p, /href="\.\.\/2026-10-rerun-pilot\/"/);
  assert.doesNotMatch(p, /\b(best|winner|beats|groundbreaking|revolutionary)\b/i);
});
