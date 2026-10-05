"""The Claude Code plugin files at the repository root."""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_plugin_manifest_matches_pyproject():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert manifest["name"] == "rerun-bench"
    bump = "bump .claude-plugin/plugin.json together with pyproject.toml"
    assert manifest["version"] == project["version"], bump
    assert manifest["license"] == project["license"]
    assert (ROOT / "skills" / "rerun-bench" / "SKILL.md").is_file()


def test_commands_run_only_when_asked_and_never_start_a_paid_run():
    files = sorted(p.name for p in (ROOT / "commands").glob("*.md"))
    assert files == ["report.md", "run-mock.md"]
    for name in files:
        text = (ROOT / "commands" / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        front = re.match(r"---\n(.*?)\n---\n", text, re.S)
        assert front, name
        assert re.search(r"^description: \S", front.group(1), re.M), name
        assert re.search(r"^disable-model-invocation: true$", front.group(1), re.M), name
        assert "Bash(uvx rerun-bench *)" in front.group(1), name
        assert "--yes" not in re.sub(r"asks for `--yes` first", "", text), name


def test_codex_manifest_matches_pyproject_and_points_at_the_icon():
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert manifest["name"] == "rerun-bench"
    assert manifest["version"] == project["version"], "bump .codex-plugin/plugin.json too"
    assert manifest["skills"] == "./skills/"
    assert len(manifest["interface"]["shortDescription"]) <= 30
    assert manifest["interface"]["composerIcon"] == "./assets/icon.svg"
    svg = (ROOT / "assets" / "icon.svg").read_text(encoding="utf-8")
    assert 'viewBox="0 0 512 512"' in svg
    assert len(svg.encode()) < 50_000
    for shot in manifest["interface"]["screenshots"]:
        assert (ROOT / shot).is_file()
