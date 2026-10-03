"""Render result sets as Markdown, JSON, or one self-contained HTML file."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .metrics import agent_metrics
from .runner import load_results


def build(results_path: Path, k: int | None = None) -> dict:
    entries = []
    for meta, runs in load_results(results_path):
        base = Path(meta["_dir"])
        diffs = {}
        for r in runs:
            p = base / r.get("diff_path", "")
            if r.get("diff_path") and p.is_file():
                diffs[(r["task_id"], r["run_index"])] = p.read_text(encoding="utf-8")
        m = agent_metrics(runs, diffs, k=k)
        models = sorted({r.get("model") for r in runs if r.get("model")})
        entries.append(
            {
                "run_id": meta["run_id"],
                "agent": meta["agent"],
                "model": meta.get("model") or (models[0] if len(models) == 1 else None),
                "models_reported": models,
                "cli_version": meta.get("cli_version"),
                "started_at": meta.get("started_at"),
                "metrics": m,
            }
        )
    entries.sort(
        key=lambda e: (
            -(e["metrics"]["pass_hat_k"] or 0),
            -(e["metrics"]["pass_rate"] or 0),
            e["run_id"],
        )
    )
    task_ids = sorted({t for e in entries for t in e["metrics"]["per_task"]})
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rerunbench_version": __version__,
        "entries": entries,
        "tasks": task_ids,
    }


# ---- formatting helpers ----------------------------------------------------------------


def _pct(x: float | None, digits: int = 0) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def _num(x: float | None, fmt: str = "{:.2f}") -> str:
    return "n/a" if x is None else fmt.format(x)


def _usd(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"${x:.4f}" if x < 1 else f"${x:.2f}"


def _ci(ci) -> str:
    return "" if not ci else f"[{100 * ci[0]:.0f}, {100 * ci[1]:.0f}]"


def _outcomes(outs: list[bool]) -> str:
    return "".join("P" if o else "F" for o in outs)


def _name(e: dict) -> str:
    return f"{e['agent']} / {e['model'] or 'default'}"


LEADER_COLS = [
    ("Agent / model", None),
    ("CLI version", None),
    ("Runs/task", None),
    ("Pass rate [95% CI]", "pass_rate"),
    ("pass@k", "pass_at_k"),
    ("pass^k", "pass_hat_k"),
    ("Flip rate", "flip_rate"),
    ("Flaky tasks", "flaky_task_fraction"),
    ("Cost/run", "mean_cost_usd"),
    ("Cost CV", "cost_cv_within_task"),
    ("Tokens CV", "tokens_cv_within_task"),
    ("Wall median", "wall_time_median_s"),
    ("Wall CV", "wall_time_cv_within_task"),
    ("Approach sim.", "approach_similarity"),
]


def _leader_cells(e: dict) -> list[tuple[str, float | None]]:
    m = e["metrics"]
    return [
        (_name(e), None),
        (e.get("cli_version") or "n/a", None),
        (str(m["min_runs_per_task"]), m["min_runs_per_task"]),
        (f"{_pct(m['pass_rate'])} {_ci(m['pass_rate_ci95'])}", m["pass_rate"]),
        (_pct(m["pass_at_k"]), m["pass_at_k"]),
        (_pct(m["pass_hat_k"]), m["pass_hat_k"]),
        (_pct(m["flip_rate"]), m["flip_rate"]),
        (_pct(m["flaky_task_fraction"]), m["flaky_task_fraction"]),
        (_usd(m["mean_cost_usd"]), m["mean_cost_usd"]),
        (_num(m["cost_cv_within_task"]), m["cost_cv_within_task"]),
        (_num(m["tokens_cv_within_task"]), m["tokens_cv_within_task"]),
        (_num(m["wall_time_median_s"], "{:.1f}s"), m["wall_time_median_s"]),
        (_num(m["wall_time_cv_within_task"]), m["wall_time_cv_within_task"]),
        (_num(m["approach_similarity"]), m["approach_similarity"]),
    ]


# ---- markdown ---------------------------------------------------------------------------


def to_markdown(rep: dict) -> str:
    lines = [
        "# rerunbench report",
        "",
        f"Generated {rep['generated_at']} by rerunbench {rep['rerunbench_version']}. "
        "k = runs per task. CV columns are the mean within-task coefficient of variation. "
        "Definitions: docs/METRICS.md.",
        "",
        "## Leaderboard",
        "",
    ]
    lines.append("| " + " | ".join(c for c, _ in LEADER_COLS) + " |")
    lines.append("|" + "---|" * len(LEADER_COLS))
    for e in rep["entries"]:
        lines.append("| " + " | ".join(c for c, _ in _leader_cells(e)) + " |")
    lines += [
        "",
        "## Per-task consistency",
        "",
        "Outcomes in run order (P = pass, F = fail), then pass rate, flip rate, and cost CV.",
        "",
    ]
    header = ["Task"] + [_name(e) for e in rep["entries"]]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for tid in rep["tasks"]:
        row = [tid]
        for e in rep["entries"]:
            t = e["metrics"]["per_task"].get(tid)
            if not t:
                row.append("not run")
                continue
            row.append(
                f"`{_outcomes(t['outcomes'])}` {_pct(t['pass_rate'])}, "
                f"flip {_pct(t['flip_rate'])}, cost CV {_num(t['cost_usd']['cv'])}"
            )
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def to_json(rep: dict) -> str:
    return json.dumps(rep, indent=2, sort_keys=False, default=str)


# ---- html ---------------------------------------------------------------------------------

CSS = """
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--card:#ffffff;
--pass:#2f7d4f;--fail:#b8433a;--accent:#2d5b9a;--chip:#f0efea}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#9a9993;
--line:#2f2e2b;--card:#1e1e1c;--pass:#5bb37f;--fail:#e0766b;--accent:#7fa8e0;--chip:#2a2a27}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 8px}
p.sub{color:var(--muted);margin:0 0 16px}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{font-weight:600;font-size:12px;color:var(--muted);cursor:pointer;user-select:none;
position:sticky;top:0;background:var(--card)}
th[data-dir="asc"]::after{content:" \\2191"}th[data-dir="desc"]::after{content:" \\2193"}
tr:last-child td{border-bottom:none}
.dots{display:inline-flex;gap:2px;vertical-align:middle;margin-right:6px}
.dot{width:9px;height:9px;border-radius:2px;display:inline-block}
.dot.p{background:var(--pass)}.dot.f{background:var(--fail)}
.cell{display:flex;align-items:center;justify-content:flex-end;gap:6px}
.small{color:var(--muted);font-size:12px}
.legend{color:var(--muted);font-size:12px;margin:8px 0}
input{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;
background:var(--card);color:var(--fg);width:min(320px,100%)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;font-size:13px}
dt{font-weight:600}dd{margin:0;color:var(--muted)}
"""

JS = """
document.querySelectorAll('table.sortable').forEach(function(t){
  t.querySelectorAll('th').forEach(function(th,i){
    th.addEventListener('click',function(){
      var dir=th.dataset.dir==='desc'?'asc':'desc';
      t.querySelectorAll('th').forEach(function(o){delete o.dataset.dir});th.dataset.dir=dir;
      var rows=Array.from(t.tBodies[0].rows);
      rows.sort(function(a,b){
        var x=a.cells[i].dataset.v, y=b.cells[i].dataset.v;
        if(x===undefined||y===undefined){x=a.cells[i].textContent;y=b.cells[i].textContent;
          return dir==='asc'?x.localeCompare(y):y.localeCompare(x)}
        x=x===''?-Infinity:parseFloat(x);y=y===''?-Infinity:parseFloat(y);
        return dir==='asc'?x-y:y-x});
      rows.forEach(function(r){t.tBodies[0].appendChild(r)});
    });
  });
});
var f=document.getElementById('taskfilter');
if(f){f.addEventListener('input',function(){var q=f.value.toLowerCase();
  document.querySelectorAll('#tasks tbody tr').forEach(function(r){
    r.style.display=r.cells[0].textContent.toLowerCase().indexOf(q)>=0?'':'none'})})}
"""


def _td(text: str, value: float | None = None, raw: bool = False) -> str:
    v = "" if value is None else f"{value:.6g}"
    body = text if raw else html.escape(text)
    attr = f' data-v="{v}"' if value is not None or text == "n/a" else ""
    return f"<td{attr}>{body}</td>"


def _dots(outs: list[bool]) -> str:
    return (
        '<span class="dots">'
        + "".join(
            f'<span class="dot {"p" if o else "f"}" title="run {i}: {"pass" if o else "fail"}">'
            "</span>"
            for i, o in enumerate(outs)
        )
        + "</span>"
    )


def to_html(rep: dict) -> str:
    e = html.escape
    head = "".join(f"<th>{e(c)}</th>" for c, _ in LEADER_COLS)
    body = []
    for ent in rep["entries"]:
        cells = _leader_cells(ent)
        tds = [
            f"<td>{e(cells[0][0])}<div class='small'>{e(ent['run_id'])}</div></td>",
            f"<td>{e(cells[1][0])}</td>",
        ]
        tds += [_td(text, val) for text, val in cells[2:]]
        body.append("<tr>" + "".join(tds) + "</tr>")
    t_head = "<th>Task</th>" + "".join(f"<th>{e(_name(x))}</th>" for x in rep["entries"])
    t_rows = []
    for tid in rep["tasks"]:
        tds = [f"<td>{e(tid)}</td>"]
        for ent in rep["entries"]:
            t = ent["metrics"]["per_task"].get(tid)
            if not t:
                tds.append("<td class='small'>not run</td>")
                continue
            sim = t["approach_similarity"]
            tip = (
                f"pass {t['passes']}/{t['n']}, 95% CI {_ci(t['pass_rate_ci95'])}, "
                f"flip {_pct(t['flip_rate'])}, cost CV {_num(t['cost_usd']['cv'])}, "
                f"wall CV {_num(t['wall_time_s']['cv'])}, approach sim {_num(sim)}"
            )
            inner = (
                f"<span class='cell' title='{e(tip)}'>{_dots(t['outcomes'])}"
                f"<span>{_pct(t['pass_rate'])}</span>"
                f"<span class='small'>flip {_pct(t['flip_rate'])}</span></span>"
            )
            tds.append(_td(inner, t["pass_rate"], raw=True))
        t_rows.append("<tr>" + "".join(tds) + "</tr>")
    k_note = ", ".join(sorted({str(x["metrics"]["k"]) for x in rep["entries"]})) or "n/a"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>rerunbench report</title><style>{CSS}</style></head>
<body><main>
<h1>rerunbench report</h1>
<p class="sub">Same task, run N times. Generated {e(rep["generated_at"])} by rerunbench
{e(rep["rerunbench_version"])}. {len(rep["entries"])} result set(s), {len(rep["tasks"])} task(s),
k = {e(k_note)}.</p>
<h2>Leaderboard</h2>
<p class="legend">Click a column to sort. CV columns are the mean within-task coefficient of
variation (std / mean across reruns of the same task).</p>
<div class="wrap"><table class="sortable" id="leaderboard"><thead><tr>{head}</tr></thead>
<tbody>{"".join(body)}</tbody></table></div>
<h2>Per-task consistency</h2>
<p class="legend">Each square is one run, in run order: green passed, red failed. Hover a cell
for CI, flip rate, cost and wall-time CV, and approach similarity.</p>
<p><input id="taskfilter" placeholder="Filter tasks" aria-label="Filter tasks"></p>
<div class="wrap"><table class="sortable" id="tasks"><thead><tr>{t_head}</tr></thead>
<tbody>{"".join(t_rows)}</tbody></table></div>
<h2>Metric definitions</h2>
<dl>
<dt>Pass rate</dt><dd>passes / runs, pooled over tasks, with a Wilson 95% interval.</dd>
<dt>pass@k</dt><dd>P(at least one of k reruns passes), unbiased estimator, averaged over
tasks.</dd>
<dt>pass^k</dt><dd>P(all k reruns pass), unbiased estimator, averaged over tasks.</dd>
<dt>Flip rate</dt><dd>P(two reruns of the same task disagree) = 2c(n-c)/(n(n-1)), averaged
over tasks.</dd>
<dt>Flaky tasks</dt><dd>Share of tasks with at least one pass and at least one fail.</dd>
<dt>Cost / tokens / wall CV</dt><dd>Sample std / mean across reruns of one task, averaged
over tasks.</dd>
<dt>Approach sim.</dt><dd>Mean pairwise Jaccard similarity of changed-line sets among passing
runs. 1.0 means every passing run made the same edit.</dd>
</dl>
</main><script>{JS}</script></body></html>
"""


RENDERERS = {"md": to_markdown, "json": to_json, "html": to_html}
