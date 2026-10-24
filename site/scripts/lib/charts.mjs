// Chart and formatting helpers. Every chart is inline SVG rendered at build
// time. Horizontal positions are percentages, so the SVG scales with its
// container without distorting marks or text. Each chart ships with a table
// view, and every mark that carries a value has a keyboard-focusable tooltip.
// Each chart is one tab stop: the first row or mark has tabindex 0, the rest
// -1, and site.js moves focus between them with the arrow keys.

export const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

export const pct = (x, digits = 0) => (x == null ? "n/a" : `${(x * 100).toFixed(digits)}%`);
export const ci = (iv) => (iv ? `[${Math.round(iv[0] * 100)}, ${Math.round(iv[1] * 100)}]` : "n/a");
/** A 95% interval in words, for places where a bare "[89, 100]" would be read as data. */
export const ciWords = (iv) => (iv ? `${Math.round(iv[0] * 100)}% to ${Math.round(iv[1] * 100)}%` : "n/a");
/** Roving tabindex: only the first item in a group is reachable with Tab. */
const tabStop = (i) => `tabindex="${i === 0 ? 0 : -1}"`;
export const int = (x) => (x == null ? "n/a" : Math.round(x).toLocaleString("en-US"));
export const usd = (x) => (x == null ? "not reported" : `$${x.toFixed(4)}`);
export const secs = (x) => (x == null ? "n/a" : `${x.toFixed(1)} s`);
export const dec = (x, d = 2) => (x == null ? "n/a" : x.toFixed(d));
export const compact = (x) => {
  if (x == null) return "n/a";
  if (Math.abs(x) >= 1e6) return `${+(x / 1e6).toFixed(2)}M`;
  if (Math.abs(x) >= 1e3) return `${+(x / 1e3).toFixed(1)}k`;
  return String(Math.round(x));
};

// Tooltip payload: first item is the value (shown strong), the rest are labels.
const tip = (lines) => esc(lines.join("\n"));

const P = (v) => `${(v * 100).toFixed(3)}%`;

function gridLines(ticks, height) {
  return ticks
    .map((t) => `<line class="grid" x1="${P(t)}" x2="${P(t)}" y1="0" y2="${height}" />`)
    .join("");
}

function axisRow(ticks, fmt, labelCol = true) {
  const labels = ticks
    .map((t, i) => {
      const anchor = i === 0 ? "start" : i === ticks.length - 1 ? "end" : "middle";
      return `<text x="${P(t)}" y="12" text-anchor="${anchor}">${esc(fmt(t))}</text>`;
    })
    .join("");
  return `<div class="crow crow-axis" aria-hidden="true">${labelCol ? '<div class="clabel"></div>' : ""}<svg class="ctrack" height="16" width="100%" overflow="visible">${labels}</svg><div class="cvalue"></div></div>`;
}

function tableView(caption, head, rows) {
  return `<details class="tableview"><summary>Show as table</summary><div class="tablewrap"><table class="data">
<caption class="sr-only">${esc(caption)}</caption>
<thead><tr>${head.map((h, i) => `<th scope="col"${i ? ' class="num"' : ""}>${esc(h)}</th>`).join("")}</tr></thead>
<tbody>${rows.map((r) => `<tr>${r.map((c, i) => (i ? `<td class="num">${esc(c)}</td>` : `<th scope="row">${esc(c)}</th>`)).join("")}</tr>`).join("")}</tbody>
</table></div></details>`;
}

const PCT_TICKS = [0, 0.25, 0.5, 0.75, 1];

// Where the estimate sits inside its interval, as a share of the interval's
// width. Marks grow out from this point when a chart animates in.
const originPct = (est, lo, hi) => (hi > lo ? `${(((est - lo) / (hi - lo)) * 100).toFixed(1)}%` : "50%");

// One row per agent: the Wilson interval as a thin bar, the estimate as a dot.
export function intervalChart({ id, title, desc, rows, compactView = false }) {
  const H = 28;
  const body = rows
    .map((r, ri) => {
      const w = Math.max(r.hi - r.lo, 0.004);
      const label = `${r.label}: ${pct(r.est)}, 95% interval ${pct(r.lo)} to ${pct(r.hi)}`;
      return `<div class="crow" ${tabStop(ri)} role="listitem" aria-label="${esc(label)}" data-tip="${tip([
        `${pct(r.est, 1)}  ${ci([r.lo, r.hi])}`,
        r.label,
        r.tipNote || "pass rate, Wilson 95% interval",
      ])}">
  <div class="clabel"><span class="cname">${esc(r.label)}</span>${r.sub ? `<span class="csub">${esc(r.sub)}</span>` : ""}</div>
  <svg class="ctrack" height="${H}" width="100%" overflow="visible" aria-hidden="true" focusable="false">
    ${gridLines(PCT_TICKS, H)}
    <rect class="ci s1" x="${P(r.lo)}" y="${H / 2 - 3}" width="${P(w)}" height="6" rx="3" style="transform-origin:${originPct(r.est, r.lo, r.hi)} 50%" />
    <circle class="est s1" cx="${P(r.est)}" cy="${H / 2}" r="5" />
  </svg>
  <div class="cvalue"><strong>${pct(r.est)}</strong> <span>${ci([r.lo, r.hi])}</span></div>
</div>`;
    })
    .join("\n");
  const table = compactView
    ? ""
    : tableView(title, ["Agent", "Pass rate", "95% low", "95% high"], rows.map((r) => [r.label, pct(r.est, 1), pct(r.lo, 1), pct(r.hi, 1)]));
  return `<figure class="chart" id="${esc(id)}" aria-labelledby="${esc(id)}-t">
  <figcaption><span class="ctitle" id="${esc(id)}-t">${esc(title)}</span>${desc ? `<span class="cdesc">${esc(desc)}</span>` : ""}</figcaption>
  <div class="cbody" role="list" data-rove>${body}
  ${axisRow(PCT_TICKS, (t) => `${t * 100}%`)}</div>
  ${table}
</figure>`;
}

const SHAPES = ["circle", "diamond", "square"];
function marker(shape, cls, cxPct, cy, size = 5) {
  if (shape === "circle") return `<circle class="${cls}" cx="${cxPct}" cy="${cy}" r="${size}" />`;
  if (shape === "square") {
    // Percent x with a pixel offset: use a nested svg positioned at cx.
    return `<svg x="${cxPct}" y="${cy}" width="1" height="1" overflow="visible"><rect class="${cls}" x="${-size}" y="${-size}" width="${size * 2}" height="${size * 2}" rx="1.5" /></svg>`;
  }
  const d = size + 1.5;
  return `<svg x="${cxPct}" y="${cy}" width="1" height="1" overflow="visible"><path class="${cls}" d="M0 ${-d} L${d} 0 L0 ${d} L${-d} 0 Z" /></svg>`;
}

function legend(series) {
  return `<ul class="legend" aria-label="Legend">${series
    .map(
      (s, i) =>
        `<li><svg width="14" height="14" aria-hidden="true" overflow="visible">${marker(SHAPES[i], `mk s${i + 1}`, "7", 7, 4.5)}</svg>${esc(s)}</li>`,
    )
    .join("")}</ul>`;
}

// Several measures on one 0..100% axis, one lane per measure so equal values
// stay visible. Used for pass^k, pass@1 and pass@k.
export function multiDotChart({ id, title, desc, series, rows }) {
  const lanes = series.length;
  const H = 12 + lanes * 10;
  const body = rows
    .map((r, ri) => {
      const vals = r.values;
      const lo = Math.min(...vals);
      const hi = Math.max(...vals);
      const marks = vals
        .map((v, i) => marker(SHAPES[i], `mk s${i + 1}`, P(v), 6 + i * 10 + 5, 4.5))
        .join("");
      const label = `${r.label}: ${series.map((s, i) => `${s} ${pct(vals[i])}`).join(", ")}`;
      return `<div class="crow" ${tabStop(ri)} role="listitem" aria-label="${esc(label)}" data-tip="${tip([
        series.map((s, i) => `${s} ${pct(vals[i], 1)}`).join("   "),
        r.label,
      ])}">
  <div class="clabel"><span class="cname">${esc(r.label)}</span>${r.sub ? `<span class="csub">${esc(r.sub)}</span>` : ""}</div>
  <svg class="ctrack" height="${H}" width="100%" overflow="visible" aria-hidden="true" focusable="false">
    ${gridLines(PCT_TICKS, H)}
    <rect class="span" x="${P(lo)}" y="${H / 2 - 1}" width="${P(Math.max(hi - lo, 0))}" height="2" />
    ${marks}
  </svg>
  <div class="cvalue"><span>gap</span> <strong>${Math.round((hi - lo) * 100)} pts</strong></div>
</div>`;
    })
    .join("\n");
  const table = tableView(title, ["Agent", ...series], rows.map((r) => [r.label, ...r.values.map((v) => pct(v, 1))]));
  return `<figure class="chart" id="${esc(id)}" aria-labelledby="${esc(id)}-t">
  <figcaption><span class="ctitle" id="${esc(id)}-t">${esc(title)}</span>${desc ? `<span class="cdesc">${esc(desc)}</span>` : ""}</figcaption>
  ${legend(series)}
  <div class="cbody" role="list" data-rove>${body}
  ${axisRow(PCT_TICKS, (t) => `${t * 100}%`)}</div>
  ${table}
</figure>`;
}

function niceTicks(max) {
  if (!(max > 0)) return [0, 1];
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const top = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(v);
  return ticks;
}

// Per task: min to max across reruns as a thin line, median as a dot. One lane
// per series (agent). Series with no data for a task draw nothing there.
export function rangeChart({ id, title, desc, series, rows, fmt = compact, unit = "" }) {
  const max = Math.max(...rows.flatMap((r) => r.values.filter(Boolean).map((v) => v.max)), 0);
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1];
  const lanes = series.length;
  const H = 10 + lanes * 10;
  const x = (v) => P(v / top);
  const body = rows
    .map((r, ri) => {
      const marks = r.values
        .map((v, i) => {
          if (!v || v.median == null) return "";
          const y = 5 + i * 10 + 5;
          return `<line class="rng s${i + 1}" x1="${x(v.min)}" x2="${x(v.max)}" y1="${y}" y2="${y}" style="transform-origin:${originPct(v.median, v.min, v.max)} 50%" />${marker(SHAPES[i], `mk s${i + 1}`, x(v.median), y, 4)}`;
        })
        .join("");
      const tipLines = r.values.map((v, i) =>
        v && v.median != null ? `${series[i]}: median ${fmt(v.median)}${unit}, ${fmt(v.min)} to ${fmt(v.max)}` : `${series[i]}: not reported`,
      );
      return `<div class="crow" ${tabStop(ri)} role="listitem" aria-label="${esc(`${r.label}. ${tipLines.join(". ")}`)}" data-tip="${tip([
        tipLines.join("\n"),
        r.label,
      ])}">
  <div class="clabel"><span class="cname mono">${esc(r.label)}</span></div>
  <svg class="ctrack" height="${H}" width="100%" overflow="visible" aria-hidden="true" focusable="false">
    ${gridLines(ticks.map((t) => t / top), H)}
    ${marks}
  </svg>
  <div class="cvalue"></div>
</div>`;
    })
    .join("\n");
  const head = ["Task", ...series.flatMap((s) => [`${s} median`, `${s} min`, `${s} max`])];
  const tRows = rows.map((r) => [r.label, ...r.values.flatMap((v) => (v && v.median != null ? [fmt(v.median), fmt(v.min), fmt(v.max)] : ["n/a", "n/a", "n/a"]))]);
  return `<figure class="chart chart-range" id="${esc(id)}" aria-labelledby="${esc(id)}-t">
  <figcaption><span class="ctitle" id="${esc(id)}-t">${esc(title)}</span>${desc ? `<span class="cdesc">${esc(desc)}</span>` : ""}</figcaption>
  ${legend(series)}
  <div class="cbody" role="list" data-rove>${body}
  ${axisRow(ticks.map((t) => t / top), (t) => fmt(t * top))}</div>
  ${tableView(title, head, tRows)}
</figure>`;
}

// Pass/fail per run. It is already a table, so it is its own table view.
export function consistencyGrid({ id, title, desc, tasks, agents }) {
  // agents: [{ label, runs: n, perTask: { [taskId]: outcomes[] } }]
  // Side by side, more than about 12 run columns no longer fit the content width
  // and the last runs scroll out of view, so larger sets get one table per agent.
  const stacked = agents.reduce((n, a) => n + a.runs, 0) > 12;
  const tables = (stacked ? agents.map((a) => [a]) : [agents]).map((group) => gridTable(title, tasks, group, stacked));
  return `<figure class="chart" id="${esc(id)}" aria-labelledby="${esc(id)}-t">
  <figcaption><span class="ctitle" id="${esc(id)}-t">${esc(title)}</span>${desc ? `<span class="cdesc">${esc(desc)}</span>` : ""}</figcaption>
  <ul class="legend" aria-label="Legend"><li><span class="run-mark pass" aria-hidden="true">&#10003;</span>pass (verifier exited 0)</li><li><span class="run-mark fail" aria-hidden="true">&#10005;</span>fail</li></ul>
  ${tables.join("\n  ")}
</figure>`;
}

// Each table is its own keyboard group: one tab stop, arrow keys inside.
function gridTable(title, tasks, agents, stacked) {
  let marks = 0;
  const head1 = agents
    .map((a) => `<th scope="colgroup" colspan="${a.runs}" class="ag">${esc(a.label)}</th><td class="rate"></td>`)
    .join("");
  const head2 = agents
    .map(
      (a) =>
        Array.from({ length: a.runs }, (_, i) => `<th scope="col" class="run"><span class="sr-only">${esc(a.label)} run </span>${i}</th>`).join("") +
        `<th scope="col" class="run rate">rate</th>`,
    )
    .join("");
  const body = tasks
    .map((t) => {
      const cells = agents
        .map((a) => {
          const out = a.perTask[t.id];
          if (!out) return `<td class="cell na" colspan="${a.runs}">not run</td><td class="cell rate"></td>`;
          const runs = Array.from({ length: a.runs }, (_, i) => {
            const o = out[i];
            if (o === undefined) return `<td class="cell na"><span class="sr-only">no run</span></td>`;
            const word = o ? "pass" : "fail";
            return `<td class="cell"><span class="run-mark ${word}" ${tabStop(marks++)} data-tip="${tip([word, `${a.label}, ${t.id}, run ${i}`])}"><span aria-hidden="true">${o ? "&#10003;" : "&#10005;"}</span><span class="sr-only">${esc(`${a.label}, ${t.id}, run ${i}: ${word}`)}</span></span></td>`;
          }).join("");
          const passes = out.filter(Boolean).length;
          return `${runs}<td class="cell rate">${passes}/${out.length}</td>`;
        })
        .join("");
      return `<tr><th scope="row"><span class="mono">${esc(t.id)}</span></th>${cells}</tr>`;
    })
    .join("\n");
  const caption = stacked ? `${title}: ${agents[0].label}` : title;
  return `<div class="tablewrap${stacked ? " grid-stacked" : ""}"><table class="grid-table" data-rove>
    <caption class="sr-only">${esc(caption)}</caption>
    <thead><tr><td></td>${head1}</tr><tr><th scope="col" class="task">Task</th>${head2}</tr></thead>
    <tbody>${body}</tbody>
  </table></div>`;
}
