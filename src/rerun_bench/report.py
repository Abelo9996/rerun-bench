"""Render result sets as terminal text, Markdown, JSON, or one self-contained HTML file."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .metrics import agent_metrics
from .runner import load_results

METRICS_URL = "https://github.com/Abelo9996/rerun-bench/blob/main/docs/METRICS.md"


def build(results_path: Path, k: int | None = None) -> dict:
    """Load every result set under ``results_path`` and compute its metrics.

    ``k`` for pass@k and pass^k defaults to the smallest runs-per-task count over all result
    sets, so every row is measured with the same k and the rows can be compared.
    """
    loaded = load_results(results_path)
    min_runs = []
    for _meta, runs in loaded:
        counts: dict[str, int] = {}
        for r in runs:
            counts[r["task_id"]] = counts.get(r["task_id"], 0) + 1
        if counts:
            min_runs.append(min(counts.values()))
    common_k = min(min_runs) if min_runs else None
    if k is not None and common_k is not None:
        common_k = min(k, common_k)
    entries = []
    for meta, runs in loaded:
        if not runs:
            continue
        base = Path(meta["_dir"])
        diffs = {}
        for r in runs:
            p = base / r.get("diff_path", "")
            if r.get("diff_path") and p.is_file():
                diffs[(r["task_id"], r["run_index"])] = p.read_text(encoding="utf-8")
        m = agent_metrics(runs, diffs, k=common_k)
        models = sorted({r.get("model") for r in runs if r.get("model")})
        planned_tasks = meta.get("tasks") or []
        planned = len(planned_tasks) * int(meta.get("runs_per_task") or 0)
        entries.append(
            {
                "run_id": meta["run_id"],
                "agent": meta["agent"],
                "model": meta.get("model") or (models[0] if len(models) == 1 else None),
                "models_reported": models,
                "cli_version": meta.get("cli_version"),
                "started_at": meta.get("started_at"),
                "simulated": meta["agent"] == "mock",
                "planned_runs": planned or None,
                "stopped": meta.get("stopped"),
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
        "rerun_bench_version": __version__,
        "k": common_k,
        "entries": entries,
        "tasks": task_ids,
        "comparison": compare(entries),
    }


def compare(entries: list[dict]) -> list[dict]:
    """Pairwise check of whether the pooled pass-rate 95% intervals overlap.

    Overlapping intervals are reported as "no established difference". Non-overlapping
    intervals are reported as a fact about the intervals, never as a winner.
    """
    out = []
    for i, a in enumerate(entries):
        for b in entries[i + 1 :]:
            (alo, ahi), (blo, bhi) = a["metrics"]["pass_rate_ci95"], b["metrics"]["pass_rate_ci95"]
            ta, tb = set(a["metrics"]["per_task"]), set(b["metrics"]["per_task"])
            out.append(
                {
                    "a": a["run_id"],
                    "b": b["run_id"],
                    "intervals_overlap": alo <= bhi and blo <= ahi,
                    "same_tasks": ta == tb,
                    "same_runs_per_task": a["metrics"]["min_runs_per_task"]
                    == b["metrics"]["min_runs_per_task"],
                }
            )
    return out


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


def _k(rep: dict) -> str:
    return str(rep["k"]) if rep.get("k") else "k"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def explanations(rep: dict) -> list[tuple[str, str]]:
    """One-line meanings of the headline metrics, with the report's actual k."""
    k = _k(rep)
    return [
        (
            "Pass rate",
            "share of runs whose hidden verifier passed, with a 95% confidence interval "
            "(Wilson). Wide intervals mean too few runs to be precise.",
        ),
        (
            f"pass^{k}",
            f"chance that {k} reruns of the same task all pass. The number to watch if you "
            "run the agent once and trust the result.",
        ),
        (f"pass@{k}", f"chance that at least one of {k} reruns passes."),
        ("Flip rate", "chance that two runs of the same task disagree (one pass, one fail)."),
        ("Flaky tasks", "share of tasks with at least one pass and at least one fail."),
        (
            "CV",
            "run-to-run spread on the same task (standard deviation / mean), averaged over "
            "tasks. 0 means identical every run.",
        ),
    ]


def warnings(e: dict) -> list[str]:
    """Plain statements a reader needs before trusting this result set's numbers."""
    m = e["metrics"]
    out = []
    if e.get("simulated"):
        out.append(
            "Simulated: the mock agent spends nothing; its cost, tokens and wall time are "
            "made up for demonstration."
        )
    if m.get("agent_error_runs"):
        out.append(
            f"{m['agent_error_runs']} of {m['n_runs']} runs ended in an agent error (non-zero "
            "exit, crash, or an error the CLI reported). They count as fails. If they are "
            "login, quota or rate-limit errors, the pass rate measures the setup, not the "
            "agent: see agent_error in runs.jsonl."
        )
    if m.get("timeout_runs"):
        out.append(
            f"{m['timeout_runs']} of {m['n_runs']} runs hit the task timeout (counted as fails)."
        )
    planned = e.get("planned_runs")
    if planned and m["n_runs"] < planned:
        why = f" ({e['stopped']})" if e.get("stopped") else ""
        out.append(
            f"Incomplete: {m['n_runs']} of {planned} planned runs recorded{why}. Continue "
            f"with `run --run-id {e['run_id']} --resume` and the same options."
        )
    if m["min_runs_per_task"] < 2:
        out.append("1 run per task: flip rate and spread need at least 2 runs per task.")
    if not e.get("simulated"):
        if m["cost_reported_runs"] == 0:
            out.append(
                "Cost: not reported by this CLI. For codex, pass prices with --agent-opt "
                "usd_per_mtok_in=... usd_per_mtok_out=..."
            )
        elif m["cost_reported_runs"] < m["n_runs"]:
            out.append(
                f"Cost: reported for {m['cost_reported_runs']} of {m['n_runs']} runs; "
                "cost figures use those runs only."
            )
    return out


def comparison_lines(rep: dict) -> list[str]:
    """Plain-language statements about whether the rows differ. Never names a winner."""
    entries = {e["run_id"]: e for e in rep["entries"]}
    if len(entries) < 2:
        return []
    pairs = rep["comparison"]
    lines = []
    if all(p["intervals_overlap"] for p in pairs):
        lines.append(
            "The pass-rate 95% intervals of all rows overlap, so these runs are not enough to "
            "tell the rows apart. More runs per task narrow the intervals."
        )
    else:
        for p in pairs:
            a, b = entries[p["a"]], entries[p["b"]]
            verdict = (
                "overlap: not enough to tell apart" if p["intervals_overlap"] else "do not overlap"
            )
            lines.append(
                f"{_name(a)} {_ci(a['metrics']['pass_rate_ci95'])} vs {_name(b)} "
                f"{_ci(b['metrics']['pass_rate_ci95'])}: intervals {verdict}."
            )
    lines.append(
        "Overlap is used as a deliberately cautious test because runs of the same task are "
        "not independent; the JSON report also has a task-bootstrap interval "
        "(macro_pass_rate_task_bootstrap_ci95)."
    )
    if any(not p["same_tasks"] or not p["same_runs_per_task"] for p in pairs):
        lines.append(
            "Not every row ran the same tasks the same number of times, so the rows are not "
            "directly comparable."
        )
    lines.append(f"Rows are sorted by pass^{_k(rep)}, then pass rate. The order is not a ranking.")
    return lines


# ---- terminal text --------------------------------------------------------------------------


def to_text(rep: dict, per_task: bool = True) -> str:
    """Narrow (80 column) plain-text report for a terminal. ASCII only."""
    k = _k(rep)
    entries = rep["entries"]
    lines = [
        f"rerun-bench report: {_plural(len(entries), 'result set')}, "
        f"{_plural(len(rep['tasks']), 'task')}, k = {k}",
    ]
    for e in entries:
        m = e["metrics"]
        sim = " (simulated)" if e.get("simulated") else ""
        lines += [
            "",
            f"{_name(e)}  [{e.get('cli_version') or 'version n/a'}]",
            f"  run id       {e['run_id']}",
            f"  Pass rate    {_pct(m['pass_rate']):>4}  {_ci(m['pass_rate_ci95']):<10} "
            f"{m['passes']} of {m['n_runs']} runs passed",
            f"  pass^{k:<7} {_pct(m['pass_hat_k']):>4}  all {k} reruns of a task pass",
            f"  pass@{k:<7} {_pct(m['pass_at_k']):>4}  at least 1 of {k} reruns passes",
            f"  Flip rate    {_pct(m['flip_rate']):>4}  two runs of the same task disagree",
            f"  Flaky tasks  {_pct(m['flaky_task_fraction']):>4}  tasks with both passes and fails",
        ]
        if m["cost_reported_runs"]:
            lines.append(
                f"  Cost/run     {_usd(m['median_cost_usd'])} median, "
                f"{_usd(m['mean_cost_usd'])} mean, CV {_num(m['cost_cv_within_task'])}{sim}"
            )
        else:
            lines.append("  Cost/run     not reported by the CLI")
        if m["tokens_median"] is not None:
            lines.append(
                f"  Tokens/run   {int(m['tokens_median'] + 0.5):,} median, "
                f"CV {_num(m['tokens_cv_within_task'])}{sim}"
            )
        lines.append(
            f"  Wall time    {_num(m['wall_time_median_s'], '{:.1f}s')} median, "
            f"CV {_num(m['wall_time_cv_within_task'])}{sim}"
        )
        for w in warnings(e):
            if e.get("simulated") and w.startswith("Simulated"):
                continue
            lines += _wrap(f"  ! {w}", indent="    ")
    comp = comparison_lines(rep)
    if comp:
        lines += ["", "Comparison"]
        for c in comp:
            lines += _wrap(f"  {c}", indent="  ")
    if per_task and rep["tasks"]:
        lines += ["", "Per task: runs in order (P pass, F fail), pass rate"]
        labels = [chr(ord("A") + i) if len(entries) > 1 else "" for i in range(len(entries))]
        if len(entries) > 1:
            for lab, e in zip(labels, entries, strict=True):
                lines.append(f"  {lab} = {_name(e)}")
        tw = max(len(t) for t in rep["tasks"])
        cols = []
        for e in entries:
            outs = [len(t["outcomes"]) for t in e["metrics"]["per_task"].values()]
            cols.append(max(outs, default=1) + 6)
        head = "  " + "task".ljust(tw)
        for lab, w in zip(labels, cols, strict=True):
            head += "  " + (lab or "runs").ljust(w)
        lines.append(head.rstrip())
        for tid in rep["tasks"]:
            row = "  " + tid.ljust(tw)
            for e, w in zip(entries, cols, strict=True):
                t = e["metrics"]["per_task"].get(tid)
                cell = f"{_outcomes(t['outcomes'])} {_pct(t['pass_rate']):>4}" if t else "not run"
                row += "  " + cell.ljust(w)
            lines.append(row.rstrip())
    lines += ["", f"Definitions: {METRICS_URL}"]
    return "\n".join(lines) + "\n"


def _wrap(text: str, width: int = 80, indent: str = "  ") -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width, subsequent_indent=indent, break_on_hyphens=False)


# ---- markdown ---------------------------------------------------------------------------


def _reliability_cells(e: dict) -> list[str]:
    m = e["metrics"]
    return [
        _name(e),
        e.get("cli_version") or "n/a",
        str(m["min_runs_per_task"]),
        f"{_pct(m['pass_rate'])} {_ci(m['pass_rate_ci95'])}",
        _pct(m["pass_hat_k"]),
        _pct(m["pass_at_k"]),
        _pct(m["flip_rate"]),
        _pct(m["flaky_task_fraction"]),
    ]


def _cost_cells(e: dict) -> list[str]:
    m = e["metrics"]
    sim = " (sim.)" if e.get("simulated") else ""
    tok = "n/a" if m["tokens_median"] is None else f"{int(m['tokens_median'] + 0.5):,}"
    return [
        _name(e),
        _usd(m["median_cost_usd"]) + (sim if m["median_cost_usd"] is not None else ""),
        _usd(m["mean_cost_usd"]),
        _num(m["cost_cv_within_task"]),
        tok,
        _num(m["tokens_cv_within_task"]),
        _num(m["wall_time_median_s"], "{:.1f}s"),
        _num(m["wall_time_cv_within_task"]),
        _num(m["approach_similarity"]),
    ]


def _reliability_head(rep: dict) -> list[str]:
    k = _k(rep)
    return [
        "Agent / model",
        "CLI version",
        "Runs/task",
        "Pass rate [95% CI]",
        f"pass^{k}",
        f"pass@{k}",
        "Flip rate",
        "Flaky tasks",
    ]


COST_HEAD = [
    "Agent / model",
    "Median cost/run",
    "Mean cost/run",
    "Cost CV",
    "Median tokens/run",
    "Tokens CV",
    "Median wall time",
    "Wall CV",
    "Approach sim.",
]


def _md_table(head: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def to_markdown(rep: dict) -> str:
    k = _k(rep)
    lines = [
        "# rerun-bench report",
        "",
        f"Generated {rep['generated_at']} by rerun-bench {rep['rerun_bench_version']}. "
        f"{_plural(len(rep['entries']), 'result set')}, {_plural(len(rep['tasks']), 'task')}, "
        f"k = {k}. Definitions: [docs/METRICS.md]({METRICS_URL}).",
        "",
    ]
    lines += [f"- **{name}**: {text}" for name, text in explanations(rep)]
    lines += ["", "## Reliability", ""]
    lines += _md_table(_reliability_head(rep), [_reliability_cells(e) for e in rep["entries"]])
    lines += ["", "## Cost and run-to-run spread", ""]
    lines += _md_table(COST_HEAD, [_cost_cells(e) for e in rep["entries"]])
    comp = comparison_lines(rep)
    if comp:
        lines += ["", "## Comparison", ""] + [" ".join(comp)]
    notes = [(e, w) for e in rep["entries"] for w in warnings(e)]
    if notes:
        lines += ["", "## Notes", ""]
        lines += [f"- {_name(e)} (`{e['run_id']}`): {w}" for e, w in notes]
    lines += [
        "",
        "## Per-task consistency",
        "",
        "Outcomes in run order (P = pass, F = fail), then pass rate, flip rate, and cost CV.",
        "",
    ]
    header = ["Task"] + [_name(e) for e in rep["entries"]]
    rows = []
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
        rows.append(row)
    lines += _md_table(header, rows)
    return "\n".join(lines) + "\n"


def to_json(rep: dict) -> str:
    return json.dumps(rep, indent=2, sort_keys=False, default=str)


# ---- html ---------------------------------------------------------------------------------

CSS = """
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--card:#ffffff;
--pass:#2f7d4f;--fail:#b8433a;--accent:#2d5b9a;--chip:#f0efea;--warn:#8a5a00;--warnbg:#fff6e0}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#9a9993;
--line:#2f2e2b;--card:#1e1e1c;--pass:#5bb37f;--fail:#e0766b;--accent:#7fa8e0;--chip:#2a2a27;
--warn:#f0c46b;--warnbg:#2a2418}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px;overflow-wrap:anywhere}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 8px}
p.sub{color:var(--muted);margin:0 0 16px}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;
overflow-wrap:normal}
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
.key{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 14px;font-size:13px;
margin:0 0 8px;padding:12px 14px;border:1px solid var(--line);border-radius:8px;
background:var(--card)}
.key dt{font-weight:600}.key dd{margin:0;color:var(--muted)}
.callout{border-left:3px solid var(--accent);padding:8px 12px;margin:12px 0;background:var(--card)}
.callout p{margin:4px 0}
.warn{border-left:3px solid var(--warn);background:var(--warnbg);padding:8px 12px;margin:12px 0}
.warn ul{margin:4px 0;padding-left:18px}
input{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;
background:var(--card);color:var(--fg);width:min(320px,100%)}
a{color:var(--accent)}
dl.defs{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 16px;font-size:13px}
dl.defs dt{font-weight:600}dl.defs dd{margin:0;color:var(--muted)}
@media (max-width:560px){.key,dl.defs{grid-template-columns:minmax(0,1fr)}
.key dd,dl.defs dd{margin-bottom:6px}}
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


def _th(label: str, tip: str = "") -> str:
    t = f' title="{html.escape(tip)}"' if tip else ""
    return f"<th{t}>{html.escape(label)}</th>"


def to_html(rep: dict) -> str:
    e = html.escape
    k = _k(rep)
    tips = dict(explanations(rep))
    rel_head = "".join(_th(c, tips.get(c, "")) for c in _reliability_head(rep))
    rel_rows = []
    cost_rows = []
    for ent in rep["entries"]:
        m = ent["metrics"]
        name_td = f"<td>{e(_name(ent))}<div class='small'>{e(ent['run_id'])}</div></td>"
        rel_rows.append(
            "<tr>"
            + name_td
            + f"<td>{e(ent.get('cli_version') or 'n/a')}</td>"
            + _td(str(m["min_runs_per_task"]), m["min_runs_per_task"])
            + _td(f"{_pct(m['pass_rate'])} {_ci(m['pass_rate_ci95'])}", m["pass_rate"])
            + _td(_pct(m["pass_hat_k"]), m["pass_hat_k"])
            + _td(_pct(m["pass_at_k"]), m["pass_at_k"])
            + _td(_pct(m["flip_rate"]), m["flip_rate"])
            + _td(_pct(m["flaky_task_fraction"]), m["flaky_task_fraction"])
            + "</tr>"
        )
        cells = _cost_cells(ent)
        vals = [
            m["median_cost_usd"],
            m["mean_cost_usd"],
            m["cost_cv_within_task"],
            m["tokens_median"],
            m["tokens_cv_within_task"],
            m["wall_time_median_s"],
            m["wall_time_cv_within_task"],
            m["approach_similarity"],
        ]
        cost_rows.append(
            "<tr>"
            + name_td
            + "".join(_td(t, v) for t, v in zip(cells[1:], vals, strict=True))
            + "</tr>"
        )
    cost_tips = {
        "Cost CV": tips["CV"],
        "Tokens CV": tips["CV"],
        "Wall CV": tips["CV"],
        "Approach sim.": "1.0 means every passing run made the same edit.",
    }
    cost_head = "".join(_th(c, cost_tips.get(c, "")) for c in COST_HEAD)
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
                f"<span>{t['passes']}/{t['n']}</span>"
                f"<span class='small'>flip {_pct(t['flip_rate'])}</span></span>"
            )
            tds.append(_td(inner, t["pass_rate"], raw=True))
        t_rows.append("<tr>" + "".join(tds) + "</tr>")
    key = "".join(f"<dt>{e(n)}</dt><dd>{e(t)}</dd>" for n, t in explanations(rep))
    comp = comparison_lines(rep)
    comp_html = (
        "<div class='callout'>" + "".join(f"<p>{e(c)}</p>" for c in comp) + "</div>" if comp else ""
    )
    notes = [(ent, w) for ent in rep["entries"] for w in warnings(ent)]
    notes_html = (
        "<div class='warn'><strong>Read before trusting these numbers</strong><ul>"
        + "".join(f"<li>{e(_name(ent))}: {e(w)}</li>" for ent, w in notes)
        + "</ul></div>"
        if notes
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>rerun-bench report</title><style>{CSS}</style></head>
<body><main>
<h1>rerun-bench report</h1>
<p class="sub">Each task was run several times by the same agent. Generated
{e(rep["generated_at"])} by rerun-bench {e(rep["rerun_bench_version"])}.
{_plural(len(rep["entries"]), "result set")}, {_plural(len(rep["tasks"]), "task")}, k = {e(k)}.</p>
<h2>How to read this</h2>
<dl class="key">{key}</dl>
{notes_html}
<h2>Reliability</h2>
{comp_html}
<div class="wrap"><table class="sortable" id="leaderboard"><thead><tr>{rel_head}</tr></thead>
<tbody>{"".join(rel_rows)}</tbody></table></div>
<p class="legend">Click a column to sort. Hover a column name for its meaning.</p>
<h2>Cost and run-to-run spread</h2>
<div class="wrap"><table class="sortable" id="cost"><thead><tr>{cost_head}</tr></thead>
<tbody>{"".join(cost_rows)}</tbody></table></div>
<p class="legend">n/a means the agent CLI did not report the value; it is never counted as
zero.</p>
<h2>Per-task consistency</h2>
<p class="legend">Each square is one run, in run order: green passed, red failed. Hover a cell
for the 95% interval, flip rate, cost and wall-time CV, and approach similarity.</p>
<p><input id="taskfilter" placeholder="Filter tasks" aria-label="Filter tasks"></p>
<div class="wrap"><table class="sortable" id="tasks"><thead><tr>{t_head}</tr></thead>
<tbody>{"".join(t_rows)}</tbody></table></div>
<h2>Metric definitions</h2>
<dl class="defs">
<dt>Pass rate</dt><dd>passes / runs, pooled over tasks, with a Wilson 95% interval. A run passes
only if the task's hidden verifier passes; the agent's own claims are not scored.</dd>
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
<dt>Full definitions</dt><dd><a href="{METRICS_URL}">docs/METRICS.md</a></dd>
</dl>
</main><script>{JS}</script></body></html>
"""


RENDERERS = {"text": to_text, "md": to_markdown, "json": to_json, "html": to_html}
