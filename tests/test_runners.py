"""Runner detection and command building (pure, no repository needed)."""

from __future__ import annotations

from rerun_bench import runners


def test_test_file_detection():
    assert runners.is_test_file("test_foo.py")
    assert runners.is_test_file("pkg/tests/test_bar.py")
    assert runners.is_test_file("src/foo_test.go")
    assert runners.is_test_file("web/app.test.js")
    assert runners.is_test_file("web/__tests__/app.mjs")
    assert not runners.is_test_file("foo.py")
    assert not runners.is_test_file("README.md")


def test_source_file_detection():
    assert runners.is_source_file("pkg/foo.py")
    assert runners.is_source_file("src/app.ts")
    assert runners.is_source_file("main.go")
    assert not runners.is_source_file("test_foo.py")  # tests are not source
    assert not runners.is_source_file("README.md")
    assert not runners.is_source_file("pyproject.toml")
    assert not runners.is_source_file("data.json")


def test_python_always_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    runner, reason = runners.detect_runner(tmp_path, "test_x.py")
    assert reason is None
    assert runner.name == "pytest" and runner.language == "python"
    assert runner.command("tests/test_x.py")[:3] == ["python", "-m", "pytest"]
    assert runner.command("tests/test_x.py")[-1] == "tests/test_x.py"


def test_python_flat_layout_has_no_editable_install(tmp_path):
    runner, _ = runners.detect_runner(tmp_path, "test_x.py")
    assert runner.setup == ["python", "-m", "pip", "install", "pytest"]


def test_go_needs_go_mod(tmp_path):
    runner, reason = runners.detect_runner(tmp_path, "pkg/foo_test.go")
    assert runner is None and "go.mod" in reason
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    runner, reason = runners.detect_runner(tmp_path, "pkg/foo_test.go")
    assert runner.name == "go"
    assert runner.command("pkg/foo_test.go") == ["go", "test", "./pkg"]


def test_javascript_node_test_vs_npm(tmp_path):
    runner, _ = runners.detect_runner(tmp_path, "app.test.js")  # no package.json
    assert runner.name == "node-test"
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "jest"}}', encoding="utf-8"
    )
    runner, _ = runners.detect_runner(tmp_path, "app.test.js")
    assert runner.name == "npm"
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "node --test"}}', encoding="utf-8"
    )
    runner, _ = runners.detect_runner(tmp_path, "app.test.js")
    assert runner.name == "node-test"


def test_non_test_file_refused(tmp_path):
    runner, reason = runners.detect_runner(tmp_path, "foo.py")
    assert runner is None and "test file" in reason


def test_root_test_js_is_a_test_file():
    assert runners.is_test_file("test.js")
    assert runners.is_test_file("test.mjs")
    assert not runners.is_test_file("src/index.js")


def test_command_selectors_narrow_the_run():
    pytest_runner = runners.Runner("pytest", "python", None)
    cmd = pytest_runner.command("tests/test_x.py", ("test_a", "test_b"))
    assert cmd[-2:] == ["-k", "test_a or test_b"]
    assert pytest_runner.command("tests/test_x.py")[-1] == "tests/test_x.py"

    node_runner = runners.Runner("node-test", "javascript", None)
    cmd = node_runner.command("test.js", ("handles empty",))
    assert "--test-name-pattern" in cmd and "handles empty" in cmd

    go_runner = runners.Runner("go", "go", None)
    assert go_runner.command("pkg/x_test.go", ("TestA", "TestB"))[-2:] == ["-run", "TestA|TestB"]
