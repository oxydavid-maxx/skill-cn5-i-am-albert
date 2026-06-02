# tests/test_search_backends.py
"""Pluggable fast search backend (C8): selection + tavily/brave shape + degrade.

The backends return the SAME {query, results, timestamp[, error]} shape as the
agentic websearch and NEVER raise — a missing key or HTTP error degrades to an
error-tagged result so the run never breaks. No live HTTP here: _http_post_json
(and brave's urlopen) are monkeypatched.
"""
import albert.search_backends as sb


def test_backend_selection_default(monkeypatch):
    monkeypatch.delenv("ALBERT_SEARCH_BACKEND", raising=False)
    assert sb.selected_backend() == "agentic"


def test_backend_selection_env(monkeypatch):
    monkeypatch.setenv("ALBERT_SEARCH_BACKEND", "tavily")
    assert sb.selected_backend() == "tavily"


def test_backend_selection_normalizes(monkeypatch):
    monkeypatch.setenv("ALBERT_SEARCH_BACKEND", "  BRAVE  ")
    assert sb.selected_backend() == "brave"


def test_tavily_shape(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setattr(
        sb, "_http_post_json",
        lambda url, payload, headers, timeout=20: {
            "results": [{"title": "T", "url": "u", "content": "passage"}],
            "answer": "ans",
        },
    )
    r = sb.tavily_search("zonal gateway competitors")
    assert r["query"] == "zonal gateway competitors"
    assert "passage" in r["results"] and "u" in r["results"]
    assert "ans" in r["results"]
    assert "timestamp" in r
    assert "error" not in r


def test_tavily_missing_key_degrades(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    r = sb.tavily_search("q")
    assert r.get("error")  # never raises; degrades
    assert r["query"] == "q"
    assert r["results"] == ""
    assert "timestamp" in r


def test_tavily_http_error_degrades(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")

    def _boom(url, payload, headers, timeout=20):
        raise ConnectionError("network down")

    monkeypatch.setattr(sb, "_http_post_json", _boom)
    r = sb.tavily_search("q")
    assert r.get("error")  # never raises
    assert "ConnectionError" in r["error"]
    assert r["results"] == ""


def test_brave_shape(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "k")

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json
            return json.dumps({
                "web": {"results": [
                    {"title": "BT", "url": "bu", "description": "bpassage"}
                ]}
            }).encode("utf-8")

    monkeypatch.setattr(sb.urllib.request, "urlopen",
                        lambda req, timeout=20: _FakeResp())
    r = sb.brave_search("zonal gateway competitors")
    assert r["query"] == "zonal gateway competitors"
    assert "bpassage" in r["results"] and "bu" in r["results"]
    assert "timestamp" in r
    assert "error" not in r


def test_brave_missing_key_degrades(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    r = sb.brave_search("q")
    assert r.get("error")
    assert r["results"] == ""
    assert "timestamp" in r


def test_websearch_dispatches_to_tavily(monkeypatch):
    """sdk_client.websearch routes to the selected backend at the top."""
    import albert.sdk_client as sc
    monkeypatch.setenv("ALBERT_SEARCH_BACKEND", "tavily")
    monkeypatch.setattr(
        sb, "tavily_search",
        lambda q: {"query": q, "results": "TAVILY", "timestamp": 1.0},
    )
    r = sc.websearch("hello")
    assert r["results"] == "TAVILY"


def test_websearch_dispatches_to_brave(monkeypatch):
    import albert.sdk_client as sc
    monkeypatch.setenv("ALBERT_SEARCH_BACKEND", "brave")
    monkeypatch.setattr(
        sb, "brave_search",
        lambda q: {"query": q, "results": "BRAVE", "timestamp": 1.0},
    )
    r = sc.websearch("hello")
    assert r["results"] == "BRAVE"


def test_websearch_agentic_default_unchanged(monkeypatch):
    """Default (agentic) backend still uses the existing _websearch_once path."""
    import albert.sdk_client as sc
    monkeypatch.delenv("ALBERT_SEARCH_BACKEND", raising=False)
    monkeypatch.setattr(
        sc, "_websearch_once",
        lambda q, max_tokens=4000: {"query": q, "results": "AGENTIC", "timestamp": 1.0},
    )
    # Reset the process latch so a prior test can't short-circuit this.
    sc._WEBSEARCH_UNAVAILABLE = False
    r = sc.websearch("hello")
    assert r["results"] == "AGENTIC"
