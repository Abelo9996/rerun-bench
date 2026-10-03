from rerun_bench import workspace as ws


def test_fresh_copy_is_isolated(tmp_path):
    src = tmp_path / "src"
    (src / "pkg" / "__pycache__").mkdir(parents=True)
    (src / "pkg" / "a.py").write_text("x = 1\n")
    (src / "pkg" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0")
    dst = ws.fresh_copy(src)
    try:
        assert (dst / "pkg" / "a.py").read_text() == "x = 1\n"
        assert not (dst / "pkg" / "__pycache__").exists()
        (dst / "pkg" / "a.py").write_text("x = 2\n")
        assert (src / "pkg" / "a.py").read_text() == "x = 1\n"
    finally:
        ws.cleanup(dst)
    assert not dst.exists()


def test_unified_diff_add_modify_delete(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "keep.txt").write_text("same\n")
    (b / "keep.txt").write_text("same\n")
    (a / "mod.py").write_text("x = 1\ny = 2\n")
    (b / "mod.py").write_text("x = 1\ny = 3\n")
    (a / "gone.txt").write_text("bye\n")
    (b / "new.txt").write_text("hi\n")
    d = ws.unified_diff(a, b)
    assert "keep.txt" not in d
    assert "--- a/mod.py" in d and "+y = 3" in d
    assert "--- a/gone.txt\n+++ /dev/null" in d
    assert "--- /dev/null\n+++ b/new.txt" in d
    lines = ws.changed_lines(d)
    assert lines == {"mod.py:-y = 2", "mod.py:+y = 3", "gone.txt:-bye", "new.txt:+hi"}
    assert ws.unified_diff(a, a) == ""


def test_changed_lines_handles_dash_content():
    diff = "--- a/x.sql\n+++ b/x.sql\n@@ -1,2 +1,2 @@\n--- old comment\n+++ new comment\n ctx\n"
    assert ws.changed_lines(diff) == {"x.sql:--- old comment", "x.sql:+++ new comment"}


def test_crlf_normalized(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "f.txt").write_bytes(b"one\r\ntwo\r\n")
    (b / "f.txt").write_bytes(b"one\ntwo\n")
    assert ws.unified_diff(a, b) == ""
