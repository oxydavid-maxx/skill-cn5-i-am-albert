"""Claude Agent SDK transport for skill-ai-escape-mrc.

Replaces albert/anthropic_client.py's subprocess CLI pattern with the official
claude-agent-sdk. Same external surface (sync call_claude, websearch) so phases
don't need async conversion.

Design contract:
- Synchronous API (call_claude, websearch) ??internally bridges to async SDK via asyncio.run.
- env={"CLAUDECODE":"", "CLAUDE_SDK_CALL":"1"} on every SDK call:
    - CLAUDECODE="" bypasses the nested-session rejection (Issue #573).
    - CLAUDE_SDK_CALL="1" triggers the superpowers SessionStart short-circuit.
- setting_sources=None ??no CLAUDE.md / auto-memory loading.
- output_format={"type":"json_schema","schema":schema} ??Claude emits schema
  data as a ToolUseBlock(name="StructuredOutput", input={...}) inside the
  AssistantMessage content, not on ResultMessage.structured_output.
- max_turns >= 2 required when schema is used (tool_use + tool_result cycle).
- OpenRouter fallback preserved for API-error cases.
- progress events emitted via albert.progress (same contract as before).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from albert.no_console import patch_anyio_open_process_for_windows

patch_anyio_open_process_for_windows()

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, query
from tenacity import retry, stop_after_attempt, wait_exponential

from albert.errors import VisibilityContractError
from albert.models import model_label


# Environment handed to every SDK call. Do not mutate per-call.
_SDK_ENV: dict[str, str] = {
    "CLAUDECODE": "",
    "CLAUDE_SDK_CALL": "1",
    # Skip the SDK's per-spawn version-check HTTP round-trip — pure startup
    # overhead, no effect on the call's output. Saves ~1-3s on every call.
    "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK": "1",
}

# Anthropic fast-mode beta header (speed="fast" + this beta per the API spec).
FAST_MODE_BETA = "fast-mode-2026-02-01"


def _fast_mode_enabled() -> bool:
    """Whether fast-mode wiring should be added to built SDK options.

    Gated on env ALBERT_FAST_MODE. DEFAULT "0" (off): the POC
    (poc/fast_mode_probe.py) found fast mode is NOT reachable on this
    CLI/subscription — the beta header is dropped for non-API-key (OAuth)
    users and the `--speed` flag does not exist in this CLI (it crashes the
    call). The wiring is kept env-gated so it engages automatically the day a
    fast-mode-capable CLI/API-key environment is used, with no code change.
    """
    return os.environ.get("ALBERT_FAST_MODE", "0") == "1"


def _apply_fast_mode(opts: dict[str, Any]) -> None:
    """When fast mode is enabled, add ONLY the non-crashing beta header.

    Deliberately does NOT add an extra_args `--speed` passthrough: the POC
    proved `--speed` is an unknown CLI option that crashes the call (exit 1).
    The beta header is the only fast-mode signal that the CLI accepts without
    erroring (it warns + ignores it for OAuth users, which is harmless).
    """
    if _fast_mode_enabled():
        opts["betas"] = [FAST_MODE_BETA]

# Process-level latch: once a tool-enabled call proves tools cannot run in this
# runtime, later calls skip the (failing, slow) tool attempt and go straight to
# the tool-less path. Avoids burning a flaky subprocess spawn per audit call.
_TOOLS_UNAVAILABLE = False

# Same idea for the dedicated websearch() path: once one query proves web search
# can't run here, later queries degrade immediately instead of each retrying.
_WEBSEARCH_UNAVAILABLE = False


def _emit(channel: str, event: str, payload: dict, **extra: Any) -> None:
    """Emit a required progress event."""
    from albert import progress as _p
    _p.emit(channel, event, payload, **extra)


async def _collect_messages(msg_iter) -> dict:
    """Iterate an SDK message async-iterator, return aggregated result.

    Returns dict with keys:
      text       - str, concatenation of all TextBlock.text (joined by '\n')
      structured - dict | None, from the first ToolUseBlock named "StructuredOutput"
      is_error   - bool, final ResultMessage.is_error (or False if absent)
      usage      - dict, final ResultMessage.usage (or {} if absent)
    """
    text_parts: list[str] = []
    structured: dict | None = None
    is_error = False
    usage: dict = {}

    async for msg in msg_iter:
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                t = getattr(block, "text", None)
                if t:
                    text_parts.append(t)
                if getattr(block, "name", None) == "StructuredOutput":
                    structured = getattr(block, "input", None)
        if hasattr(msg, "is_error"):
            is_error = bool(getattr(msg, "is_error", False))
        if hasattr(msg, "usage"):
            u = getattr(msg, "usage", None)
            if isinstance(u, dict):
                usage = u

    return {
        "text": "\n".join(text_parts),
        "structured": structured,
        "is_error": is_error,
        "usage": usage,
    }


async def _sdk_query(
    *,
    prompt: str,
    system_prompt: str,
    model: str | None,
    schema: dict | None,
    timeout_sec: int,
    max_turns: int,
    allow_tools: bool = False,
) -> dict:
    """Run one SDK query with skill-ai-escape-mrc's standard options.

    When ``allow_tools`` is true the WebSearch tool is permitted so audit
    phases can verify/benchmark claims mid-round (matches the prompts that
    instruct the model to "Use WebSearch ..."). Otherwise no tools are allowed.

    Returns the dict produced by `_collect_messages`.
    Raises asyncio.TimeoutError on timeout.
    """
    opts_kwargs: dict[str, Any] = dict(
        system_prompt=system_prompt,
        setting_sources=None,
        allowed_tools=["WebSearch"] if allow_tools else [],
        max_turns=max_turns,
        env=dict(_SDK_ENV),
    )
    if model:
        opts_kwargs["model"] = model
    if schema is not None:
        opts_kwargs["output_format"] = {"type": "json_schema", "schema": schema}
    _apply_fast_mode(opts_kwargs)

    options = ClaudeAgentOptions(**opts_kwargs)

    async def _run():
        return await _collect_messages(query(prompt=prompt, options=options))

    return await asyncio.wait_for(_run(), timeout=timeout_sec)


def _dump_parse_failure(text: str, context: str = "") -> None:
    """Save failed text to runs/_parse_failures/ for post-mortem.

    Mirrors anthropic_client.py:_dump_parse_failure. Best-effort only.
    """
    try:
        import datetime
        dump_dir = Path(__file__).parent.parent / "runs" / "_parse_failures"
        dump_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dump = dump_dir / f"{ts}_{context}.txt"
        dump.write_text(text, encoding="utf-8")
    except Exception:
        pass


def _extract_json(text: str):
    """Robust JSON extraction with multiple fallback strategies.

    Strategies tried in order:
      1. Bare JSON (standalone object or array)
      2. Fenced code block (```json ... ``` or plain ```)
      3. Embedded in prose (outermost balanced braces/brackets)

    Raises json.JSONDecodeError if all strategies fail; also dumps to
    runs/_parse_failures/ for debugging.
    """
    if not text or not text.strip():
        raise json.JSONDecodeError("empty input", text or "", 0)

    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    for pat in (
        r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```",
        r"```\s*(\{.*?\}|\[.*?\])\s*```",
    ):
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue

    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        start = text.find(open_ch)
        while start != -1:
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\" and in_string:
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
            start = text.find(open_ch, start + 1)

    _dump_parse_failure(text, "extract_json_all_strategies_failed")
    raise json.JSONDecodeError(
        f"no valid JSON found in text (first 300 chars: {text[:300]!r})",
        text,
        0,
    )


def _should_retry(retry_state) -> bool:
    """Retry on transport/network errors, NOT on JSONDecodeError.

    JSON parse failures are deterministic given same prompt.
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is None:
        return False
    if isinstance(exc, (json.JSONDecodeError, VisibilityContractError)):
        return False
    return True


@retry(stop=stop_after_attempt(8), wait=wait_exponential(min=3, max=60),
       retry=_should_retry, reraise=True)
def call_claude(
    model: str | None,
    system: str,
    user: str,
    parse_json: bool = False,
    max_tokens: int = 8000,
    temperature: float = 0.3,
    purpose: str = "unknown",
    allow_tools: bool = False,
    json_schema: dict | None = None,
    timeout_sec: int = 600,
):
    # WIKI-CONSULTED: silent-staleness#misleading-metadata-trap
    # WIKI-FINDING: 600s default is fine for short-prompt phases; phase_7_report's
    #   123K-token input prompt + large markdown output consistently exceeds 10 min
    #   and crashes with TimeoutError, producing no report despite Phases 0-6 being
    #   complete. Anthropic API default is 60 min; our 10 min was arbitrary.
    # WIKI-ACTION: made timeout per-call overridable; phase_7_report.py now passes
    #   timeout_sec=1800 (30 min) for the report-render call while other phases
    #   keep the 600s default.
    """Call Claude via the Agent SDK. Drop-in replacement for the legacy
    anthropic_client.call_claude.

    Signature and return shapes match the legacy module:
      - text mode           -> str
      - json_schema != None -> dict (schema-conformant)
      - parse_json=True     -> dict (best-effort JSON parse)

    `max_tokens`, `temperature` are accepted for signature compatibility with
    the legacy caller; the SDK version ignores them (delegated to the claude
    CLI's own model config). `allow_tools=True` permits the WebSearch tool for
    the duration of the call so audit phases can verify claims in-round (and
    bumps max_turns to leave room for the tool_use/tool_result cycle on top of
    any schema cycle).

    On SDK failure: raises. No provider-level fallback. @retry(3x) handles
    transient transport errors; deterministic failures propagate.
    """
    log_model = model_label(model)
    _emit("llm", "llm_call_start",
          {"purpose": purpose, "prompt_len": len(user)}, model=log_model)

    def _run(use_tools: bool) -> dict:
        return asyncio.run(_sdk_query(
            prompt=user,
            system_prompt=system.rstrip(),
            model=model,
            schema=json_schema,
            timeout_sec=timeout_sec,
            max_turns=5 if use_tools else 3,
            allow_tools=use_tools,
        ))

    global _TOOLS_UNAVAILABLE
    if allow_tools and not _TOOLS_UNAVAILABLE:
        # Tool use is optional augmentation (audit phases "Use WebSearch if ...").
        # If the tool-enabled call cannot run in this environment, degrade to a
        # tool-less call so the phase still produces real output instead of
        # collapsing to a fallback stub. JSON/visibility errors are not masked.
        try:
            result = _run(True)
        except (json.JSONDecodeError, VisibilityContractError):
            raise
        except Exception as tool_exc:
            _TOOLS_UNAVAILABLE = True
            _emit("llm", "llm_tool_unavailable",
                  {"purpose": purpose, "error": f"{type(tool_exc).__name__}: {str(tool_exc)[:200]}"},
                  model=log_model)
            result = _run(False)
    else:
        result = _run(False)

    if json_schema is not None:
        so = result.get("structured")
        if so is None:
            raise RuntimeError(
                f"SDK schema call returned no structured output "
                f"(is_error={result['is_error']}, text_len={len(result['text'])})"
            )
        _emit("llm", "llm_call_end",
              {"purpose": purpose, "text_len": len(json.dumps(so))}, model=log_model)
        return so

    text = result["text"]
    if not text:
        raise RuntimeError(
            f"SDK returned empty text (is_error={result['is_error']}, "
            f"purpose={purpose})"
        )

    _emit("llm", "llm_call_end",
          {"purpose": purpose, "text_len": len(text)}, model=log_model)

    if parse_json:
        try:
            return _extract_json(text)
        except json.JSONDecodeError:
            _dump_parse_failure(text, f"{purpose}_first_attempt")
            raise
    return text


async def _session_turn(client: ClaudeSDKClient, user: str, timeout_sec: int) -> dict:
    """Run one turn on an already-connected ClaudeSDKClient and aggregate it."""
    async def _run():
        await client.query(user)
        return await _collect_messages(client.receive_response())

    return await asyncio.wait_for(_run(), timeout=timeout_sec)


class ClaudeSession:
    """Persistent ClaudeSDKClient session: connect one subprocess, run many turns.

    The default transport (`call_claude` -> `query()`) spawns a fresh `claude`
    CLI subprocess per call, paying session-startup overhead every time. When a
    phase issues several calls that share one system prompt + schema and form a
    natural conversation (e.g. the sequential audit rounds, where round N+1
    reacts to round N), routing them through ONE persistent session pays that
    startup once and cuts the number of spawns (which, on a flaky transport,
    also cuts retry storms).

    Each turn's user prompt should remain self-contained enough to be correct
    even if the underlying connection is lost and transparently reconnected.

    Usage:
        with ClaudeSession(system=sys, model=m, schema=SCHEMA, allow_tools=True) as s:
            r1 = s.ask(user1, purpose="round_1")
            r2 = s.ask(user2, purpose="round_2")

    `ask()` returns a schema dict when `schema` was given, else the text string.
    On a turn failure it retries (transport errors only) and reconnects a dead
    session before giving up; JSON/visibility errors are not masked.
    """

    def __init__(self, *, system: str, model: str | None = None,
                 schema: dict | None = None, allow_tools: bool = False,
                 timeout_sec: int = 600, max_attempts: int = 8,
                 max_turns: int | None = None):
        self._system = system.rstrip()
        self._model = model
        self._schema = schema
        self._timeout = timeout_sec
        self._max_attempts = max_attempts
        # Optional cap on tool_use turns. Each WebSearch costs one turn, so a low
        # value (e.g. 3) bounds how many times an audit can search the web mid-turn.
        self._max_turns = max_turns
        # Honour the process-wide latch: never connect with tools we already
        # know cannot run in this runtime.
        self._tools = allow_tools and not _TOOLS_UNAVAILABLE
        self._loop: Any = None
        self._client: ClaudeSDKClient | None = None

    def _build_options(self) -> ClaudeAgentOptions:
        opts: dict[str, Any] = dict(
            system_prompt=self._system,
            setting_sources=None,
            allowed_tools=["WebSearch"] if self._tools else [],
            max_turns=self._max_turns if self._max_turns is not None else (5 if self._tools else 3),
            env=dict(_SDK_ENV),
        )
        if self._model:
            opts["model"] = self._model
        if self._schema is not None:
            opts["output_format"] = {"type": "json_schema", "schema": self._schema}
        _apply_fast_mode(opts)
        return ClaudeAgentOptions(**opts)

    def _connect(self) -> None:
        self._client = ClaudeSDKClient(options=self._build_options())
        self._loop.run_until_complete(self._client.connect())

    def _disconnect(self) -> None:
        if self._client is not None:
            try:
                self._loop.run_until_complete(self._client.disconnect())
            except Exception:
                pass
            self._client = None

    def __enter__(self) -> "ClaudeSession":
        self._loop = asyncio.new_event_loop()
        try:
            self._connect()
        except Exception:
            # Connecting with tools failed -> fall back to a tool-less session.
            if self._tools:
                self._tools = False
                self._disconnect()
                self._connect()
            else:
                raise
        return self

    def __exit__(self, *exc) -> None:
        self._disconnect()
        try:
            self._loop.close()
        except Exception:
            pass
        self._loop = None

    def _finalize(self, result: dict, purpose: str, log_model: str):
        if self._schema is not None:
            so = result.get("structured")
            if so is None:
                raise RuntimeError(
                    f"SDK schema session turn returned no structured output "
                    f"(is_error={result['is_error']}, text_len={len(result['text'])})"
                )
            _emit("llm", "llm_call_end",
                  {"purpose": purpose, "text_len": len(json.dumps(so))}, model=log_model)
            return so
        text = result["text"]
        if not text:
            raise RuntimeError(f"SDK session turn returned empty text (purpose={purpose})")
        _emit("llm", "llm_call_end",
              {"purpose": purpose, "text_len": len(text)}, model=log_model)
        return text

    def ask(self, user: str, purpose: str = "unknown"):
        global _TOOLS_UNAVAILABLE
        log_model = model_label(self._model)
        _emit("llm", "llm_call_start",
              {"purpose": purpose, "prompt_len": len(user), "session": True}, model=log_model)

        last_exc: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                result = self._loop.run_until_complete(
                    _session_turn(self._client, user, self._timeout)
                )
                return self._finalize(result, purpose, log_model)
            except (json.JSONDecodeError, VisibilityContractError):
                raise
            except Exception as exc:  # transport / process error
                last_exc = exc
                # If we were using tools and they're the problem, drop to a
                # tool-less session for the remainder.
                if self._tools:
                    _TOOLS_UNAVAILABLE = True
                    self._tools = False
                    _emit("llm", "llm_tool_unavailable",
                          {"purpose": purpose, "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
                          model=log_model)
                if attempt < self._max_attempts:
                    time.sleep(min(60, 3 * (2 ** (attempt - 1))))
                    # Reconnect a (possibly dead) session before retrying.
                    self._disconnect()
                    try:
                        self._connect()
                    except Exception:
                        pass
        raise last_exc if last_exc else RuntimeError(f"session turn failed (purpose={purpose})")


def _degraded_websearch(query_text: str, reason: str) -> dict:
    """Empty, error-tagged web-search result so callers can degrade gracefully."""
    return {"query": query_text, "results": "", "error": reason, "timestamp": time.time()}


# Two attempts only: web search is OPTIONAL augmentation (phase_0). When the
# runtime simply cannot run it, more retries just flood the screen and waste
# minutes — the latch below short-circuits the rest of the batch.
@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=15),
       retry=_should_retry, reraise=True)
def _websearch_once(query_text: str, max_tokens: int = 4000) -> dict:
    system_prompt = "You are a web research assistant. Use the WebSearch tool when asked."
    user_prompt = (
        f"Please use the WebSearch tool to search for: {query_text}\n\n"
        "Then provide the top 3 findings with source URLs and brief summaries. "
        "Format as plain text with clear URL citations."
    )

    # Least-privilege: allow only the WebSearch tool. We deliberately do NOT use
    # permission_mode="bypassPermissions" — that maps to --dangerously-skip-
    # permissions, which is rejected under root and is unnecessary for a single
    # whitelisted tool.
    opts = ClaudeAgentOptions(
        system_prompt=system_prompt,
        setting_sources=None,
        allowed_tools=["WebSearch"],
        max_turns=5,
        env=dict(_SDK_ENV),
    )

    async def _run():
        return await _collect_messages(query(prompt=user_prompt, options=opts))

    result = asyncio.run(asyncio.wait_for(_run(), timeout=180))
    text = result["text"]
    if not text:
        raise RuntimeError("SDK websearch returned empty text")
    return {
        "query": query_text,
        "results": text.strip(),
        "timestamp": time.time(),
    }


def websearch(query_text: str, max_tokens: int = 4000) -> dict:
    """Web search via Agent SDK. Returns {query, results, timestamp[, error]}.

    Never raises: web search is optional augmentation, so a failure returns an
    empty, error-tagged result instead of aborting the caller. Once a query
    proves web search is unavailable in this runtime, a process-wide latch makes
    every later query degrade immediately (no SDK call, no retry) so the screen
    isn't flooded and the run isn't stalled on doomed searches.
    """
    global _WEBSEARCH_UNAVAILABLE
    _emit("websearch", "search_start", {"query": query_text[:80]})

    if _WEBSEARCH_UNAVAILABLE:
        return _degraded_websearch(
            query_text, "web search unavailable in this runtime (latched after an earlier failure)"
        )

    try:
        result = _websearch_once(query_text, max_tokens)
        _emit("websearch", "search_end",
              {"query": query_text[:80], "text_len": len(result["results"])})
        return result
    except (json.JSONDecodeError, VisibilityContractError):
        raise
    except Exception as e:
        _WEBSEARCH_UNAVAILABLE = True
        _emit("websearch", "search_unavailable",
              {"query": query_text[:80], "error": f"{type(e).__name__}: {str(e)[:150]}"})
        return _degraded_websearch(query_text, f"{type(e).__name__}: {str(e)[:200]}")
