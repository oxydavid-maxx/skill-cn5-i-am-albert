"""Fast search backend reachability probe (gate for the C8 pluggable backend).

For each HTTP backend whose API key env var is present (TAVILY_API_KEY /
BRAVE_API_KEY), run ONE real query and print the wall-clock latency + a short
result excerpt so we can confirm (a) the key works and (b) the returned content
is usable for grounding. Backends with no key are reported as "no key" — that is
expected and fine (the production wiring degrades to an error-tagged result and
the run falls back to the agentic backend).

Run:  py -3 poc/search_backend_probe.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Make the repo importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from albert import search_backends as sb

QUERY = "zonal gateway automotive ethernet competitors 2026"


def _probe(name: str, key_env: str, fn) -> None:
    print(f"\n=== {name} ===", flush=True)
    if not os.environ.get(key_env):
        print(f"  no key ({key_env} unset) — skipping live call. "
              f"Production wiring degrades to an error-tagged result here.",
              flush=True)
        # Still call once to prove the degrade path returns the right shape.
        r = fn(QUERY)
        print(f"  degrade shape: error={r.get('error')!r} "
              f"results_len={len(r.get('results',''))} "
              f"has_timestamp={'timestamp' in r}", flush=True)
        return
    t0 = time.time()
    r = fn(QUERY)
    dt = time.time() - t0
    if r.get("error"):
        print(f"  FAIL latency={dt:.2f}s error={r['error']}", flush=True)
        return
    excerpt = (r.get("results") or "")[:400].replace("\n", " ")
    print(f"  OK   latency={dt:.2f}s results_len={len(r.get('results',''))}", flush=True)
    print(f"       excerpt: {excerpt}", flush=True)


def main() -> None:
    print("Selected backend (ALBERT_SEARCH_BACKEND):", sb.selected_backend())
    _probe("tavily", "TAVILY_API_KEY", sb.tavily_search)
    _probe("brave", "BRAVE_API_KEY", sb.brave_search)

    print("\n========== SUMMARY ==========")
    present = [k for k in ("TAVILY_API_KEY", "BRAVE_API_KEY") if os.environ.get(k)]
    if present:
        print("Keys present:", ", ".join(present))
        print("→ those backends are usable; set ALBERT_SEARCH_BACKEND accordingly.")
    else:
        print("No search-API keys present (TAVILY_API_KEY / BRAVE_API_KEY both unset).")
        print("→ C8 fast backends are wired + tested but cannot be measured here; "
              "they engage automatically once a key is set. Default 'agentic' "
              "backend is unaffected.")


if __name__ == "__main__":
    main()
