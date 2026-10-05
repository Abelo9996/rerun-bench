"""The GitHub Action's metadata and its outputs script (action/outputs.py)."""

import importlib.util
import re

from rerun_bench import __version__, cli
from rerun_bench import report as report_mod

from .conftest import REPO, TASKS_DIR

ACTION = (REPO / "action.yml").read_text(encoding="utf-8")


def _outputs_module():
    spec = importlib.util.spec_from_file_location(
        "rb_action_outputs", REPO / "action" / "outputs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _input_default(name: str) -> str:
    m = re.search(rf"\n  {name}:\n(?:    .*\n)*?    default: (.*)\n", ACTION)
    assert m, name
    return m.group(1).strip('"')


def test_action_defaults():
    # The default is the newest release on PyPI, which can trail the version in this checkout.
    default = tuple(int(x) for x in _input_default("version").split("."))
    assert default <= tuple(int(x) for x in __version__.split("."))
    assert _input_default("agent") == "mock", "the action is free out of the box"
    assert _input_default("report-format") in report_mod.RENDERERS
    assert re.search(r"\nbranding:\n  icon: repeat\n  color: purple\n", ACTION)
    for name in ["pass-rate", "pass-rate-low", "pass-rate-high", "flip-rate"]:
        assert f"\n  {name}:\n" in ACTION


def test_outputs_and_summary(tmp_path, monkeypatch):
    out = tmp_path / "results"
    args = ["--tasks-dir", str(TASKS_DIR), "run", "--agent", "mock", "--tasks"]
    args += ["edit-config,minimal-fix", "--runs", "3", "--out", str(out), "--run-id", "r1"]
    assert cli.main([*args, "--quiet", "--no-report"]) == 0
    rep = report_mod.build(out / "r1")
    report_json = tmp_path / "report.json"
    report_json.write_text(report_mod.to_json(rep), encoding="utf-8")
    summary_txt = tmp_path / "summary.txt"
    summary_txt.write_text(report_mod.to_text(rep), encoding="utf-8")
    gh_out = tmp_path / "gh_output"
    gh_summary = tmp_path / "gh_summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(gh_summary))
    mod = _outputs_module()
    argv = ["outputs.py", str(report_json), str(summary_txt), "rd", "rp"]
    assert mod.main(argv) == 0
    outs = dict(line.split("=", 1) for line in gh_out.read_text().splitlines())
    m = rep["entries"][0]["metrics"]
    assert outs["runs"] == "6"
    assert float(outs["pass-rate"]) == round(m["passes"] / 6, 4)
    lo, hi = float(outs["pass-rate-low"]), float(outs["pass-rate-high"])
    assert 0 <= lo <= float(outs["pass-rate"]) <= hi <= 1
    assert float(outs["flip-rate"]) == round(m["flip_rate"], 4)
    assert outs["k"] == "3" and outs["run-dir"] == "rd" and outs["report-path"] == "rp"
    md = gh_summary.read_text()
    assert md.startswith("## rerun-bench\n\n**mock / mock-1**: ")
    assert "Simulated by the mock agent" in md
    assert "```text\nrerun-bench report: 1 result set, 2 tasks, k = 3" in md


def test_fmt_fractions():
    fmt = _outputs_module().fmt
    assert [fmt(x) for x in (0.8, 0.0, 1.0, 0.123456, None)] == ["0.8", "0", "1", "0.1235", ""]


def test_example_workflow_uses_the_action():
    wf = (REPO / "examples" / "rerun-bench.yml").read_text(encoding="utf-8")
    assert "uses: Abelo9996/rerun-bench@v0" in wf
    assert "workflow_dispatch" in wf, "real agents only run when started by hand"
