import importlib
run_albert = importlib.import_module("run_albert")


class _FakeStream:
    def __init__(self, isatty_value):
        self._tty = isatty_value

    def isatty(self):
        return self._tty


class _NoIsatty:
    pass


def _tty_pair():
    return (_FakeStream(True), _FakeStream(True))


def test_allowed_when_interactive():
    assert run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=False, dry_run=False, streams=_tty_pair()) is None


def test_refused_when_a_stream_not_tty():
    msg = run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=False, dry_run=False,
        streams=(_FakeStream(True), _FakeStream(False)))
    assert msg is not None
    assert "拒絕執行" in msg
    assert "--allow-redirect" in msg


def test_cockpit_exempt():
    assert run_albert._redirect_refusal(
        is_cockpit=True, allow_redirect=False, dry_run=False,
        streams=(_FakeStream(False), _FakeStream(False))) is None


def test_allow_redirect_exempt():
    assert run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=True, dry_run=False,
        streams=(_FakeStream(False), _FakeStream(False))) is None


def test_dry_run_exempt():
    assert run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=False, dry_run=True,
        streams=(_FakeStream(False), _FakeStream(False))) is None


def test_stream_without_isatty_treated_as_not_tty():
    msg = run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=False, dry_run=False,
        streams=(_NoIsatty(),))
    assert msg is not None
