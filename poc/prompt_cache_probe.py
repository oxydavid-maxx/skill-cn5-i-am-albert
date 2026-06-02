"""Prompt-caching reachability probe (gate for the prompt-cache speedup work).

Builds a ~2K-token STATIC system prompt and issues TWO `call_claude`-style SDK
calls with cache wiring, printing the ResultMessage.usage block each time. We
look for `cache_creation_input_tokens` (1st call writes the cache) and
`cache_read_input_tokens` (2nd call reads it). If those appear and the 2nd
call's read tokens > 0, prompt caching is REACHABLE on this CLI/subscription.

The SDK `ClaudeAgentOptions` exposes `system_prompt` as a plain string — there
is no per-block `cache_control` surface. So the probe tries the plausible
SDK→CLI passthroughs that *might* engage Anthropic's prompt cache:
  - betas=["prompt-caching-2024-07-31"]   (the prompt-caching beta header)
  - extra_args / settings passthroughs
plus a control with no cache wiring, and REPORTS which (if any) produced
cache_* usage tokens.

Run:  py -3 poc/prompt_cache_probe.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Make the repo importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from albert.no_console import patch_anyio_open_process_for_windows

patch_anyio_open_process_for_windows()

from claude_agent_sdk import ClaudeAgentOptions, query

_SDK_ENV = {
    "CLAUDECODE": "",
    "CLAUDE_SDK_CALL": "1",
    "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK": "1",
}

# The prompt-caching beta header per the Anthropic API spec.
CACHE_BETA = "prompt-caching-2024-07-31"

# A ~2K-token static system prompt (repeated stable content). Caching only
# kicks in above a model-specific minimum (1024 tokens for Sonnet), so we make
# it comfortably large and IDENTICAL across both calls.
_BLOCK = (
    "You are an automotive systems reviewer. The following reference material is "
    "stable across the entire session and should be cached. "
)
SYSTEM = (_BLOCK + (
    "Reference: CAN bus arbitration uses dominant (0) and recessive (1) bits; "
    "nodes monitor the bus while transmitting the identifier and back off on "
    "detecting a dominant bit where they sent recessive. ISO 11898 defines the "
    "physical and data-link layers. AUTOSAR Classic vs Adaptive differ in OS "
    "and communication stacks. ASPICE SYS.2 requires bidirectional traceability "
    "between stakeholder needs and system requirements. Functional safety per "
    "ISO 26262 assigns ASIL levels A through D based on severity, exposure and "
    "controllability. Zonal architectures consolidate ECUs by physical location "
    "and rely on high-bandwidth backbones (automotive Ethernet) plus a central "
    "compute. "
) * 12)  # repeated to push well past the 1024-token cache minimum

USER = "In one short sentence, name the ISO standard that defines CAN."


async def _collect_usage(msg_iter) -> dict:
    usage: dict = {}
    text_parts: list[str] = []
    async for msg in msg_iter:
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                t = getattr(block, "text", None)
                if t:
                    text_parts.append(t)
        if hasattr(msg, "usage"):
            u = getattr(msg, "usage", None)
            if isinstance(u, dict):
                usage = u
    return {"usage": usage, "text": "\n".join(text_parts)}


def _run_call(label: str, *, betas=None, extra_args=None, settings=None) -> dict:
    kwargs = dict(
        system_prompt=SYSTEM,
        setting_sources=None,
        allowed_tools=[],
        max_turns=2,
        env=dict(_SDK_ENV),
    )
    if betas is not None:
        kwargs["betas"] = betas
    if extra_args is not None:
        kwargs["extra_args"] = extra_args
    if settings is not None:
        kwargs["settings"] = settings

    t0 = time.time()
    try:
        options = ClaudeAgentOptions(**kwargs)

        async def _go():
            return await _collect_usage(query(prompt=USER, options=options))

        res = asyncio.run(asyncio.wait_for(_go(), timeout=300))
        dt = time.time() - t0
        u = res["usage"]
        return {
            "label": label, "ok": True, "elapsed": dt, "usage": u,
            "cache_creation": u.get("cache_creation_input_tokens"),
            "cache_read": u.get("cache_read_input_tokens"),
            "error": None,
        }
    except Exception as e:  # noqa: BLE001 — probe records any failure
        dt = time.time() - t0
        return {"label": label, "ok": False, "elapsed": dt, "usage": {},
                "cache_creation": None, "cache_read": None,
                "error": f"{type(e).__name__}: {str(e)[:300]}"}


def _probe_variant(name: str, **wiring) -> list[dict]:
    """Run the SAME cache wiring twice in a row (write then read)."""
    out = []
    for i in (1, 2):
        print(f"\n=== {name} — call {i} ===", flush=True)
        r = _run_call(f"{name} call{i}", **wiring)
        out.append(r)
        if r["ok"]:
            print(f"  OK   elapsed={r['elapsed']:.1f}s  usage={r['usage']}", flush=True)
            print(f"       cache_creation_input_tokens={r['cache_creation']}  "
                  f"cache_read_input_tokens={r['cache_read']}", flush=True)
        else:
            print(f"  FAIL elapsed={r['elapsed']:.1f}s  error={r['error']}", flush=True)
    return out


def main() -> None:
    variants = [
        ("control (no cache wiring)", dict()),
        ("betas=[prompt-caching]", dict(betas=[CACHE_BETA])),
    ]

    all_results: dict[str, list[dict]] = {}
    for name, wiring in variants:
        all_results[name] = _probe_variant(name, **wiring)

    print("\n========== SUMMARY ==========")
    cache_seen = False
    for name, pair in all_results.items():
        for r in pair:
            if r["ok"] and (r["cache_creation"] or r["cache_read"]):
                cache_seen = True
            status = "OK  " if r["ok"] else "FAIL"
            print(f"  [{status}] {r['label']:30s} elapsed={r['elapsed']:6.1f}s "
                  f"cache_creation={r['cache_creation']} cache_read={r['cache_read']}")
            if not r["ok"]:
                print(f"           -> {r['error']}")

    print("\nPrompt caching reachable:",
          "YES (cache_* tokens appeared)" if cache_seen
          else "NO (no cache_creation/cache_read tokens in any usage block)")
    print("Note: usage blocks above are the ground truth. If every usage block "
          "lacks cache_* keys, caching is not engaged on this transport/subscription.")


if __name__ == "__main__":
    main()
