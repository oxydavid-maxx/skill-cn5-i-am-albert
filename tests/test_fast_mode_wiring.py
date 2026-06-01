# tests/test_fast_mode_wiring.py
"""Fast-mode env-gated wiring for the SDK option construction.

The POC (poc/fast_mode_probe.py) found fast mode is NOT reachable on this
CLI/subscription: the `--speed` flag does not exist (crashes the CLI) and the
beta header is dropped for non-API-key users. So:
  - wiring is gated on env ALBERT_FAST_MODE, DEFAULT "0" (off),
  - when ON we add ONLY the non-crashing beta header (never an extra_args
    --speed passthrough, which the POC proved crashes the CLI),
  - when OFF the built options carry no fast-mode beta.

These assert on the built ClaudeAgentOptions object — no live SDK call.
"""
import albert.sdk_client as sc
from albert.sdk_client import FAST_MODE_BETA, _fast_mode_enabled, _apply_fast_mode


def test_default_is_off(monkeypatch):
    monkeypatch.delenv("ALBERT_FAST_MODE", raising=False)
    assert _fast_mode_enabled() is False


def test_env_1_enables(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODE", "1")
    assert _fast_mode_enabled() is True


def test_env_0_disables(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODE", "0")
    assert _fast_mode_enabled() is False


def test_apply_adds_beta_when_enabled(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODE", "1")
    opts = {}
    _apply_fast_mode(opts)
    assert opts.get("betas") == [FAST_MODE_BETA]
    # Never wire the crashing --speed passthrough.
    assert "extra_args" not in opts


def test_apply_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODE", "0")
    opts = {}
    _apply_fast_mode(opts)
    assert "betas" not in opts
    assert "extra_args" not in opts


def test_sdk_query_options_carry_beta_when_enabled(monkeypatch):
    """_sdk_query must build options carrying the beta when fast mode is on."""
    monkeypatch.setenv("ALBERT_FAST_MODE", "1")
    captured = {}

    class _FakeOptions:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(sc, "ClaudeAgentOptions", _FakeOptions)

    async def _fake_collect(_):
        return {"text": "x", "structured": None, "is_error": False, "usage": {}}

    monkeypatch.setattr(sc, "_collect_messages", _fake_collect)
    monkeypatch.setattr(sc, "query", lambda **k: iter(()))

    import asyncio
    asyncio.run(sc._sdk_query(prompt="p", system_prompt="s", model=None,
                              schema=None, timeout_sec=5, max_turns=3))
    assert captured.get("betas") == [FAST_MODE_BETA]
    assert "extra_args" not in captured


def test_sdk_query_options_no_beta_when_disabled(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODE", "0")
    captured = {}

    class _FakeOptions:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(sc, "ClaudeAgentOptions", _FakeOptions)

    async def _fake_collect(_):
        return {"text": "x", "structured": None, "is_error": False, "usage": {}}

    monkeypatch.setattr(sc, "_collect_messages", _fake_collect)
    monkeypatch.setattr(sc, "query", lambda **k: iter(()))

    import asyncio
    asyncio.run(sc._sdk_query(prompt="p", system_prompt="s", model=None,
                              schema=None, timeout_sec=5, max_turns=3))
    assert "betas" not in captured


def test_session_build_options_carry_beta_when_enabled(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODE", "1")
    captured = {}

    class _FakeOptions:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(sc, "ClaudeAgentOptions", _FakeOptions)
    sess = sc.ClaudeSession(system="s", model=None)
    sess._build_options()
    assert captured.get("betas") == [FAST_MODE_BETA]
    assert "extra_args" not in captured


def test_session_build_options_no_beta_when_disabled(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODE", "0")
    captured = {}

    class _FakeOptions:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(sc, "ClaudeAgentOptions", _FakeOptions)
    sess = sc.ClaudeSession(system="s", model=None)
    sess._build_options()
    assert "betas" not in captured
