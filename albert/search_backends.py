"""Pluggable search backends. Each returns {query, results, timestamp[, error]} —
the same shape as the agentic websearch — and NEVER raises (degrades to
error-tagged). Selection is env-driven (ALBERT_SEARCH_BACKEND, default
"agentic"); the tavily/brave HTTP backends kill the ~150s agentic-search floor
when an API key is present, and degrade harmlessly to an error-tagged result
when the key is absent so the run never breaks."""
import os
import time
import json
import urllib.request


def selected_backend() -> str:
    return (os.environ.get("ALBERT_SEARCH_BACKEND") or "agentic").strip().lower()


def _http_post_json(url, payload, headers, timeout=20):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tavily_search(query: str) -> dict:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return {"query": query, "results": "", "error": "TAVILY_API_KEY unset",
                "timestamp": time.time()}
    try:
        data = _http_post_json(
            "https://api.tavily.com/search",
            {"api_key": key, "query": query, "search_depth": "basic",
             "include_answer": True, "max_results": 5},
            {},
        )
        parts = []
        if data.get("answer"):
            parts.append(data["answer"])
        for r in data.get("results", []):
            parts.append(
                f"- {r.get('title','')} ({r.get('url','')}): "
                f"{str(r.get('content',''))[:400]}"
            )
        return {"query": query, "results": "\n".join(parts), "timestamp": time.time()}
    except Exception as e:
        return {"query": query, "results": "",
                "error": f"{type(e).__name__}: {str(e)[:200]}", "timestamp": time.time()}


def brave_search(query: str) -> dict:
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        return {"query": query, "results": "", "error": "BRAVE_API_KEY unset",
                "timestamp": time.time()}
    try:
        import urllib.parse
        url = ("https://api.search.brave.com/res/v1/web/search?q="
               + urllib.parse.quote(query))
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "X-Subscription-Token": key},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = [
            f"- {w.get('title','')} ({w.get('url','')}): "
            f"{str(w.get('description',''))[:300]}"
            for w in (data.get("web", {}) or {}).get("results", [])[:5]
        ]
        return {"query": query, "results": "\n".join(parts), "timestamp": time.time()}
    except Exception as e:
        return {"query": query, "results": "",
                "error": f"{type(e).__name__}: {str(e)[:200]}", "timestamp": time.time()}
