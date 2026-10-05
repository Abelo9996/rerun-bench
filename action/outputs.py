"""Read a rerun-bench JSON report and write GitHub Actions outputs and a summary header.

Used by action.yml. Standard library only, so it runs with any Python 3.8+.

Usage: python outputs.py <report.json> <summary.txt> <run-dir> <report-file>
"""

from __future__ import annotations

import json
import os
import sys


def fmt(x) -> str:
    """A fraction with up to 4 decimals and no trailing zeros; empty when undefined."""
    if x is None:
        return ""
    return f"{x:.4f}".rstrip("0").rstrip(".") or "0"


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def outputs(rep: dict) -> dict:
    e = rep["entries"][0]
    m = e["metrics"]
    lo, hi = m["pass_rate_ci95"]
    return {
        "pass-rate": fmt(m["pass_rate"]),
        "pass-rate-low": fmt(lo),
        "pass-rate-high": fmt(hi),
        "flip-rate": fmt(m["flip_rate"]),
        "pass-hat-k": fmt(m["pass_hat_k"]),
        "k": "" if m["k"] is None else str(m["k"]),
        "runs": str(m["n_runs"]),
        "passes": str(m["passes"]),
        "agent-errors": str(m["agent_error_runs"]),
    }


def headline(rep: dict) -> str:
    e = rep["entries"][0]
    m = e["metrics"]
    lo, hi = m["pass_rate_ci95"]
    model = e.get("model") or "default"
    line = (
        f"**{e['agent']} / {model}**: {m['passes']} of {m['n_runs']} runs passed, "
        f"pass rate {pct(m['pass_rate'])} (95% interval {pct(lo)} to {pct(hi)}), "
        f"flip rate {pct(m['flip_rate'])}, pass^{m['k']} {pct(m['pass_hat_k'])}."
    )
    if e.get("simulated"):
        line += " Simulated by the mock agent: nothing was spent and cost and time are made up."
    return line


def main(argv: list[str]) -> int:
    report_json, summary_txt, run_dir, report_file = argv[1:5]
    with open(report_json, encoding="utf-8") as f:
        rep = json.load(f)
    if not rep.get("entries"):
        print("error: the report has no result set", file=sys.stderr)
        return 1
    outs = outputs(rep)
    outs["run-dir"] = run_dir
    outs["report-path"] = report_file
    for k, v in outs.items():
        print(f"{k}={v}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in outs.items())
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_txt, encoding="utf-8") as f:
            text = f.read().replace("```", "'''")
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(
                "## rerun-bench\n\n" + headline(rep) + "\n\n```text\n" + text.rstrip() + "\n```\n\n"
            )
            f.write(
                "The results directory and the report are attached to this run as artifacts.\n\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
