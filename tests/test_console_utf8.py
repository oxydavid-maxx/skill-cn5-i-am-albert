import importlib
run_albert = importlib.import_module("run_albert")


class _FakeStream:
    def __init__(self, raise_on_reconfigure=False):
        self.calls = []
        self._raise = raise_on_reconfigure

    def reconfigure(self, **kwargs):
        if self._raise:
            raise ValueError("cannot reconfigure")
        self.calls.append(kwargs)


def test_force_utf8_console_sets_utf8_replace_linebuffered():
    s = _FakeStream()
    run_albert._force_utf8_console([s])
    assert s.calls == [{"encoding": "utf-8", "errors": "replace", "line_buffering": True}]


def test_force_utf8_console_swallows_reconfigure_error():
    s = _FakeStream(raise_on_reconfigure=True)
    run_albert._force_utf8_console([s])  # must not raise
    assert s.calls == []


def test_deliberation_banner_contains_label_and_path(tmp_path):
    out = run_albert._deliberation_banner(tmp_path)
    assert "辯論過程" in out
    assert "deliberation.md" in out
    assert str(tmp_path) in out
