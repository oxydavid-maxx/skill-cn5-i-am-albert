# tests/test_prompt_cache_wiring.py
"""Prompt-cache env-gated wiring for the SDK option construction.

POC finding (poc/prompt_cache_probe.py): prompt caching is ALREADY engaged
automatically on this OAuth CLI/subscription (the control variant showed
cache_creation then cache_read_input_tokens > 0 on a repeat call). The explicit
prompt-caching beta header is IGNORED for non-API-key users, so the wiring is a
harmless no-op on OAuth but engages on an API-key transport with no code change.
Therefore:
  - wiring is gated on env ALBERT_PROMPT_CACHE, DEFAULT "0" (off),
  - when ON we add the prompt-caching beta header (merged with any existing
    betas, e.g. fast mode),
  - when OFF the built options carry no prompt-caching beta.

These assert on the built option dict — no live SDK call.
"""
import albert.sdk_client as sc
from albert.sdk_client import (
    PROMPT_CACHE_BETA,
    FAST_MODE_BETA,
    _prompt_cache_enabled,
    _apply_prompt_cache,
)


def test_default_is_off(monkeypatch):
    monkeypatch.delenv("ALBERT_PROMPT_CACHE", raising=False)
    assert _prompt_cache_enabled() is False


def test_env_1_enables(monkeypatch):
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "1")
    assert _prompt_cache_enabled() is True


def test_env_0_disables(monkeypatch):
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "0")
    assert _prompt_cache_enabled() is False


def test_apply_adds_beta_when_enabled(monkeypatch):
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "1")
    opts = {}
    _apply_prompt_cache(opts)
    assert opts.get("betas") == [PROMPT_CACHE_BETA]


def test_apply_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "0")
    opts = {}
    _apply_prompt_cache(opts)
    assert "betas" not in opts


def test_apply_merges_with_existing_betas(monkeypatch):
    """Must not clobber a beta already set (e.g. fast mode)."""
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "1")
    opts = {"betas": [FAST_MODE_BETA]}
    _apply_prompt_cache(opts)
    assert FAST_MODE_BETA in opts["betas"]
    assert PROMPT_CACHE_BETA in opts["betas"]


def test_apply_no_duplicate(monkeypatch):
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "1")
    opts = {"betas": [PROMPT_CACHE_BETA]}
    _apply_prompt_cache(opts)
    assert opts["betas"].count(PROMPT_CACHE_BETA) == 1


def test_sdk_query_options_carry_beta_when_enabled(monkeypatch):
    """_sdk_query must build options carrying the cache beta when enabled."""
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "1")
    monkeypatch.delenv("ALBERT_FAST_MODE", raising=False)
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
    assert captured.get("betas") == [PROMPT_CACHE_BETA]


def test_sdk_query_options_no_beta_when_disabled(monkeypatch):
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "0")
    monkeypatch.delenv("ALBERT_FAST_MODE", raising=False)
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
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "1")
    monkeypatch.delenv("ALBERT_FAST_MODE", raising=False)
    captured = {}

    class _FakeOptions:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(sc, "ClaudeAgentOptions", _FakeOptions)
    sess = sc.ClaudeSession(system="s", model=None)
    sess._build_options()
    assert captured.get("betas") == [PROMPT_CACHE_BETA]


def test_session_build_options_no_beta_when_disabled(monkeypatch):
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "0")
    monkeypatch.delenv("ALBERT_FAST_MODE", raising=False)
    captured = {}

    class _FakeOptions:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(sc, "ClaudeAgentOptions", _FakeOptions)
    sess = sc.ClaudeSession(system="s", model=None)
    sess._build_options()
    assert "betas" not in captured


def test_fast_mode_and_cache_coexist(monkeypatch):
    """Both betas present when both env flags are on (merge, no clobber)."""
    monkeypatch.setenv("ALBERT_PROMPT_CACHE", "1")
    monkeypatch.setenv("ALBERT_FAST_MODE", "1")
    captured = {}

    class _FakeOptions:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(sc, "ClaudeAgentOptions", _FakeOptions)
    sess = sc.ClaudeSession(system="s", model=None)
    sess._build_options()
    assert FAST_MODE_BETA in captured["betas"]
    assert PROMPT_CACHE_BETA in captured["betas"]
