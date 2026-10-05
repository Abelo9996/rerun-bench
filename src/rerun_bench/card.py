"""A 1200x630 SVG result card (the size X, Bluesky and link previews use) for posting.

Built from the same numbers as ``report``. It shows the agents compared, the pass rate with
its 95% Wilson interval drawn as a bar with whiskers, pass^k, flip rate, median cost, the
number of tasks and runs, the date, and one plain sentence about the comparison. The
sentence never names a winner: overlapping intervals are reported as "no established
difference", and non-overlapping ones only as a fact about the intervals.

Plain SVG with the system font stack and no dependencies. Colors follow the open-agent-lab
site. Light colors are presentation attributes, so renderers that ignore CSS still draw the
light card; a prefers-color-scheme media query switches to the dark palette where CSS is
supported.
"""

from __future__ import annotations

from .report import _usd

WIDTH = 1200
HEIGHT = 630
REPO = "github.com/Abelo9996/rerun-bench"
COMMAND = "uvx rerun-bench"
MAX_ROWS = 4

AGENT_NAME = {"claude": "Claude Code", "codex": "Codex CLI", "opencode": "opencode", "mock": "mock"}

# Words a comparison sentence must never contain. Tests check every sentence against this.
WINNER_WORDS = ("better", "worse", "best", "win", "beat", "outperform", "leads", "superior")

LIGHT = {
    "bg": "#f2f5f3",
    "surface": "#fcfdfc",
    "ink": "#0f1614",
    "ink2": "#39443f",
    "muted": "#5a6661",
    "rule": "#cdd6d1",
    "grid": "#e0e6e3",
    "axis": "#b5c0bb",
    "accent": "#0a6650",
    "accentSoft": "#c4e2d7",
    "signal": "#d4ef3f",
    "signalInk": "#182000",
}
DARK = {
    "bg": "#0c1110",
    "surface": "#151b1a",
    "ink": "#e7eeeb",
    "ink2": "#b7c3be",
    "muted": "#91a09a",
    "rule": "#2c3734",
    "grid": "#242e2b",
    "axis": "#3d4a46",
    "accent": "#5fd0ad",
    "accentSoft": "#1f4a3f",
    "signal": "#cdea45",
    "signalInk": "#182000",
}

SANS = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
MONO = (
    "ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', "
    "'Liberation Mono', monospace"
)

PAD = 64
RIGHT = WIDTH - PAD


# ---- the numbers and the sentence ----------------------------------------------------


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _display_names(entries: list[dict]) -> dict[str, str]:
    """Agent name, plus the model when two rows share an agent."""
    labels = {e["run_id"]: AGENT_NAME.get(e["agent"], e["agent"]) for e in entries}
    counts: dict[str, int] = {}
    for v in labels.values():
        counts[v] = counts.get(v, 0) + 1
    out = {}
    for e in entries:
        base = labels[e["run_id"]]
        model = e["model"] or "default"
        if counts[base] == 1:
            out[e["run_id"]] = base
        elif model.startswith(e["agent"]):
            out[e["run_id"]] = model  # mock-steady, not "mock mock-steady"
        else:
            out[e["run_id"]] = f"{base} {model}"
    return out


def _join(names: list[str]) -> str:
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def sentence(rep: dict) -> str:
    """One plain sentence about what the result shows. Never names a winner."""
    entries = rep["entries"]
    names = _display_names(entries)
    if len(entries) == 1:
        e = entries[0]
        m = e["metrics"]
        return (
            f"{names[e['run_id']]} passed {m['passes']} of {m['n_runs']} runs "
            f"({_pct(m['pass_rate'])}, 95% interval {_ci(m['pass_rate_ci95'])})"
        )
    pairs = rep["comparison"]
    if any(not p["same_tasks"] or not p["same_runs_per_task"] for p in pairs):
        return (
            "These rows ran different tasks or run counts, so their pass rates are not "
            "directly comparable"
        )
    if all(p["intervals_overlap"] for p in pairs):
        who = _join([names[e["run_id"]] for e in entries])
        return (
            f"The 95% intervals of {who} overlap, so these runs do not establish a "
            "difference in pass rate"
        )
    apart = [p for p in pairs if not p["intervals_overlap"]]
    if len(pairs) == 1:
        a, b = names[apart[0]["a"]], names[apart[0]["b"]]
        return f"The 95% intervals of {a} and {b} do not overlap"
    return f"{len(apart)} of {len(pairs)} pairs of 95% pass-rate intervals do not overlap"


def _ci(ci) -> str:
    return f"[{100 * ci[0]:.0f}, {100 * ci[1]:.0f}]"


def _date(entries: list[dict]) -> str | None:
    dates = sorted({(e.get("started_at") or "")[:10] for e in entries} - {""})
    if not dates:
        return None
    return dates[0] if dates[0] == dates[-1] else f"{dates[0]} to {dates[-1]}"


def card_model(rep: dict) -> dict:
    """Everything the card shows, as plain values. Rows are in name order, not ranked."""
    entries = rep["entries"]
    names = _display_names(entries)
    k = rep.get("k")
    rows = []
    for e in sorted(entries, key=lambda e: (names[e["run_id"]].lower(), e["run_id"])):
        m = e["metrics"]
        cost = m.get("median_cost_usd")
        rows.append(
            {
                "name": names[e["run_id"]],
                "agent": e["agent"],
                "model": e.get("model") or "default model",
                "simulated": bool(e.get("simulated")),
                "pass_rate": m["pass_rate"],
                "ci": m["pass_rate_ci95"],
                "passes": m["passes"],
                "runs": m["n_runs"],
                "pass_hat_k": m.get("pass_hat_k"),
                "flip_rate": m.get("flip_rate"),
                "cost": None if cost is None else _usd(cost),
            }
        )
    n_tasks = sorted({e["metrics"]["n_tasks"] for e in entries})
    per_task = sorted({e["metrics"]["min_runs_per_task"] for e in entries})
    return {
        "sentence": sentence(rep),
        "rows": rows[:MAX_ROWS],
        "more": max(0, len(rows) - MAX_ROWS),
        "k": k,
        "tasks": n_tasks[0] if len(n_tasks) == 1 else None,
        "runs_per_task": per_task[0] if len(per_task) == 1 else None,
        "total_runs": sum(e["metrics"]["n_runs"] for e in entries),
        "date": _date(entries),
        "simulated": any(e.get("simulated") for e in entries),
    }


def from_report_json(data: dict) -> dict:
    """A report saved with ``report --format json`` (any version), ready for ``card_model``.

    Older reports lack the comparison, the simulated flag and the top-level k; they are
    filled in from the entries.
    """
    from .report import compare

    entries = [dict(e) for e in data.get("entries") or []]
    for e in entries:
        e.setdefault("simulated", e.get("agent") == "mock")
    ks = {e["metrics"].get("k") for e in entries}
    k = data.get("k") or (ks.pop() if len(ks) == 1 else None)
    return {**data, "entries": entries, "k": k, "comparison": compare(entries)}


# ---- text measurement ------------------------------------------------------------------

_W: dict[str, int] = {}
for chars, w in [
    ("0123456789abdeghnopqu$#?_", 556),
    ("ckszvxy", 500),
    ("fjt/!.,:;[] '|", 278),
    ("il", 222),
    ("r()-", 333),
    ("mM", 833),
    ("w", 722),
    ("ABEKPSVXY", 667),
    ("CDHNRU", 722),
    ("GOQ", 778),
    ("FTZ", 611),
    ("L", 556),
    ("J", 500),
    ("I", 278),
    ("W", 944),
    ("%", 889),
]:
    for c in chars:
        _W[c] = w


def text_width(s: str, size: float, bold: bool = False) -> float:
    """Estimated width in Helvetica/Arial metrics, kept on the wide side."""
    units = sum(_W.get(c, 600) for c in s)
    return units / 1000 * size * (1.1 if bold else 1.05) * 1.04


def mono_width(s: str, size: float) -> float:
    return len(s) * size * 0.602


def _fit_mono(s: str, size: float, width: float) -> str:
    if mono_width(s, size) <= width:
        return s
    keep = max(1, int(width / (size * 0.602)) - 1)
    return s[:keep].rstrip() + "…"


def _fit_text(s: str, size: float, width: float, bold: bool) -> str:
    if text_width(s, size, bold) <= width:
        return s
    while len(s) > 1 and text_width(s + "…", size, bold) > width:
        s = s[:-1]
    return s.rstrip() + "…"


def wrap(s: str, size: float, width: float, bold: bool) -> list[str]:
    lines: list[str] = []
    cur = ""
    for w in s.split():
        nxt = f"{cur} {w}" if cur else w
        if cur and text_width(nxt, size, bold) > width:
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines


def _fit_headline(s: str, width: float) -> tuple[int, list[str]]:
    for size in (48, 44, 40, 36):
        lines = wrap(s, size, width, True)
        if len(lines) <= 2:
            return size, lines
    lines = wrap(s, 34, width, True)
    return 34, [lines[0], _fit_text(" ".join(lines[1:]), 34, width, True)]


# ---- SVG -------------------------------------------------------------------------------


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _fill(t: str) -> str:
    return f'class="f-{t}" fill="{LIGHT[t]}"'


def _stroke(t: str) -> str:
    return f'class="s-{t}" stroke="{LIGHT[t]}"'


def _style() -> str:
    rules = "".join(f".f-{t}{{fill:{c}}}.s-{t}{{stroke:{c}}}" for t, c in DARK.items())
    return f"<style>@media (prefers-color-scheme: dark){{{rules}}}</style>"


def _n(x: float) -> str:
    """Coordinates with at most one decimal."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _text(
    s: str,
    x: float,
    y: float,
    size: float,
    color: str,
    weight: int | None = None,
    mono: bool = False,
    anchor: str = "start",
    spacing: float | None = None,
) -> str:
    attrs = [f'x="{_n(x)}"', f'y="{_n(y)}"', f'font-size="{_n(size)}"']
    if weight:
        attrs.append(f'font-weight="{weight}"')
    if mono:
        attrs.append(f'font-family="{MONO}"')
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if spacing:
        attrs.append(f'letter-spacing="{_n(spacing)}"')
    attrs.append(_fill(color))
    return f"<text {' '.join(attrs)}>{_esc(s)}</text>"


def _ruler() -> str:
    minor = "".join(f"M{x + 0.5} 0V7" for x in range(0, WIDTH + 1, 8) if x % 80)
    major = "".join(f"M{x + 0.5} 0V18" for x in range(0, WIDTH + 1, 80))
    return (
        f'<path d="{minor}" stroke-width="1" {_stroke("axis")}/>'
        f'<path d="{major}" stroke-width="1.5" {_stroke("ink2")}/>'
    )


def _logo(x: float, y: float, s: float) -> str:
    k = s / 32
    out = ""
    for bx, by, h, t in (
        (3, 12, 17, "ink"),
        (10, 5, 24, "ink"),
        (17, 15, 14, "ink"),
        (24, 5, 24, "accent"),
    ):
        out += (
            f'<rect x="{_n(x + bx * k)}" y="{_n(y + by * k)}" width="{_n(5 * k)}" '
            f'height="{_n(h * k)}" rx="{_n(k)}" {_fill(t)}/>'
        )
    return out


def _footer() -> str:
    y = 568
    h = HEIGHT - y
    base = y + h / 2 + 8
    size = 20
    left = "measured with rerun-bench"
    left_w = mono_width(left, size)
    cmd_w = mono_width(COMMAND, size) + 24
    gap = (RIGHT - PAD - left_w - cmd_w - mono_width(REPO, size)) / 2
    cmd_x = PAD + left_w + gap
    dot = lambda x: _text("·", x, base, size, "bg", mono=True, anchor="middle")  # noqa: E731
    return "".join(
        [
            f'<rect x="0" y="{y}" width="{WIDTH}" height="{h}" {_fill("ink")}/>',
            _text(left, PAD, base, size, "bg", mono=True),
            dot(cmd_x - gap / 2),
            f'<rect x="{_n(cmd_x)}" y="{_n(base - 25)}" width="{_n(cmd_w)}" height="36" rx="4" '
            f"{_fill('signal')}/>",
            _text(COMMAND, cmd_x + cmd_w / 2, base, size, "signalInk", 700, True, "middle"),
            dot(cmd_x + cmd_w + gap / 2),
            _text(REPO, RIGHT, base, size, "bg", mono=True, anchor="end"),
        ]
    )


# Column layout of the results table.
NAME_X = PAD
RATE_R = 452  # right edge of the pass-rate number
CHART_L, CHART_R = 480, 740  # the 0 to 100% axis
HATK_R, FLIP_R, COST_R = 860, 985, RIGHT


def render_svg(model: dict) -> str:
    out: list[str] = [f'<rect width="{WIDTH}" height="{HEIGHT}" {_fill("bg")}/>', _ruler()]

    # Header: mark, name, date and the simulated label.
    out.append(_logo(PAD, 56, 36))
    out.append(_text("rerun-bench", PAD + 50, 86, 32, "ink", 700, spacing=-0.3))
    right = RIGHT
    if model["simulated"]:
        w = mono_width("SIMULATED", 18) + 24
        out.append(
            f'<rect x="{_n(right - w)}" y="58" width="{_n(w)}" height="34" rx="4" '
            f'fill="none" stroke-width="2" {_stroke("ink")}/>'
        )
        out.append(_text("SIMULATED", right - w / 2, 81, 18, "ink", 700, True, "middle", 1))
        right -= w + 20
    if model["date"]:
        out.append(_text(model["date"], right, 84, 22, "muted", mono=True, anchor="end"))

    # The plain sentence.
    size, lines = _fit_headline(model["sentence"] + ".", RIGHT - PAD)
    lh = round(size * 1.14)
    y = 116 + size
    for i, line in enumerate(lines):
        out.append(_text(line, PAD, y + i * lh, size, "ink", 760, spacing=-0.5))
    y += (len(lines) - 1) * lh

    # Table header.
    k = model["k"] or "k"
    head_y = y + 62
    hs = 19
    for (l1, l2), xr in (
        (("pass rate", "95% interval"), RATE_R),
        (("", f"pass^{k}"), HATK_R),
        (("flip", "rate"), FLIP_R),
        (("median", "cost/run"), COST_R),
    ):
        if l1:
            out.append(_text(l1, xr, head_y - 23, hs, "muted", mono=True, anchor="end"))
        out.append(_text(l2, xr, head_y, hs, "muted", mono=True, anchor="end"))

    rows = model["rows"]
    top = head_y + 14
    bottom = 500
    row_h = min(96, (bottom - top) / max(1, len(rows)))
    scale = (CHART_R - CHART_L) / 1.0
    # Gridlines at 0, 50 and 100% behind the bars, labeled under the last row.
    for frac in (0, 0.5, 1):
        gx = CHART_L + frac * scale
        out.append(
            f'<path d="M{_n(gx)} {_n(top)}V{_n(top + row_h * len(rows))}" stroke-width="1" '
            f"{_stroke('axis' if frac == 0 else 'grid')}/>"
        )
    for i, r in enumerate(rows):
        ry = top + i * row_h
        out.append(f'<path d="M{PAD} {_n(ry + 0.5)}H{RIGHT}" stroke-width="1" {_stroke("rule")}/>')
        mid = ry + row_h / 2
        # Name and model.
        out.append(
            _text(
                _fit_text(r["name"], 26, RATE_R - 120 - NAME_X, True),
                NAME_X,
                mid - 3,
                26,
                "ink",
                650,
            )
        )
        model_line = r["model"] if r["model"] != r["name"] else f"{r['agent']} agent"
        model_line += " · simulated" if r["simulated"] else ""
        out.append(
            _text(
                _fit_mono(model_line, 18, RATE_R - 110 - NAME_X),
                NAME_X,
                mid + 25,
                18,
                "muted",
                mono=True,
            )
        )
        # Pass rate and interval as numbers.
        out.append(_text(_pct(r["pass_rate"]), RATE_R, mid - 1, 30, "ink", 700, True, "end"))
        out.append(_text(_ci(r["ci"]), RATE_R, mid + 25, 18, "muted", mono=True, anchor="end"))
        # Bar from 0 to the pass rate, whiskers over the 95% interval.
        bh = 22
        bw = max(0.0, (r["pass_rate"] or 0) * scale)
        out.append(
            f'<rect x="{CHART_L}" y="{_n(mid - bh / 2)}" width="{_n(bw)}" height="{bh}" rx="2" '
            f"{_fill('accentSoft')}/>"
        )
        lo, hi = CHART_L + r["ci"][0] * scale, CHART_L + r["ci"][1] * scale
        out.append(
            f'<path d="M{_n(lo)} {_n(mid)}H{_n(hi)}M{_n(lo)} {_n(mid - 13)}V{_n(mid + 13)}'
            f'M{_n(hi)} {_n(mid - 13)}V{_n(mid + 13)}" stroke-width="2.5" fill="none" '
            f'stroke-linecap="round" {_stroke("ink")}/>'
        )
        px = CHART_L + (r["pass_rate"] or 0) * scale
        out.append(
            f'<circle cx="{_n(px)}" cy="{_n(mid)}" r="6" stroke-width="2" '
            f'class="f-accent s-bg" fill="{LIGHT["accent"]}" stroke="{LIGHT["bg"]}"/>'
        )
        # pass^k, flip rate, cost.
        for val, xr in ((_pct(r["pass_hat_k"]), HATK_R), (_pct(r["flip_rate"]), FLIP_R)):
            out.append(_text(val, xr, mid + 10, 28, "ink", 700, True, "end"))
        cost = r["cost"] or "n/a"
        out.append(
            _text(cost, COST_R, mid + 10, 28, "ink" if r["cost"] else "muted", 700, True, "end")
        )
        if r["simulated"] and r["cost"]:
            out.append(_text("simulated", COST_R, mid + 34, 16, "muted", mono=True, anchor="end"))
    table_end = top + row_h * len(rows)
    out.append(
        f'<path d="M{PAD} {_n(table_end + 0.5)}H{RIGHT}" stroke-width="1" {_stroke("rule")}/>'
    )
    for frac, label in ((0, "0"), (0.5, "50"), (1, "100%")):
        anchor = "start" if frac == 0 else "end" if frac == 1 else "middle"
        out.append(
            _text(
                label, CHART_L + frac * scale, table_end + 24, 18, "muted", mono=True, anchor=anchor
            )
        )

    # What was run, just above the footer.
    parts = []
    if model["tasks"]:
        parts.append(f"{model['tasks']} task{'s' if model['tasks'] != 1 else ''}")
    if model["runs_per_task"]:
        parts.append(
            f"{model['runs_per_task']} run{'s' if model['runs_per_task'] != 1 else ''} each"
        )
    parts.append(f"{model['total_runs']} runs in all")
    parts.append("Wilson 95% intervals")
    if any(r["cost"] is None for r in rows):
        parts.append("n/a: cost not reported")
    if model["more"]:
        parts.append(f"+{model['more']} more not shown")
    out.append(
        _text(_fit_mono(" · ".join(parts), 20, RIGHT - PAD), PAD, 548, 20, "muted", mono=True)
    )

    out.append(_footer())

    names = "; ".join(
        f"{r['name']} ({r['model']}{', simulated' if r['simulated'] else ''}): pass rate "
        f"{_pct(r['pass_rate'])} {_ci(r['ci'])}, pass^{k} {_pct(r['pass_hat_k'])}, "
        f"flip rate {_pct(r['flip_rate'])}, median cost {r['cost'] or 'n/a'}"
        for r in rows
    )
    sim = (
        " Simulated with the mock agent: nothing was spent and costs are made up."
        if model["simulated"]
        else ""
    )
    desc = f"{model['sentence']}. {names}.{sim} Measured with rerun-bench: {COMMAND}, {REPO}."
    title = model["sentence"]
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="rb-title rb-desc" '
            f'font-family="{SANS}">',
            f'<title id="rb-title">{_esc(title)}</title>',
            f'<desc id="rb-desc">{_esc(desc)}</desc>',
            _style(),
            *out,
            "</svg>",
            "",
        ]
    )


def to_svg(rep: dict) -> str:
    return render_svg(card_model(rep))
