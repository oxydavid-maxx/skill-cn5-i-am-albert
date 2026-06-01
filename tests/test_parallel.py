# tests/test_parallel.py
import threading
import time

import pytest

from albert.parallel import parallel_map, parallel_run, DEFAULT_MAX_WORKERS


def test_default_max_workers_is_six():
    assert DEFAULT_MAX_WORKERS == 6


def test_empty_list_returns_empty():
    assert parallel_map(lambda x: x * 2, []) == []
    assert parallel_run([]) == []


def test_single_item_runs_inline():
    # With a single item the helper must NOT spawn a pool — verify it runs on
    # the calling thread (inline fast path keeps small-N deterministic).
    calling_thread = threading.get_ident()
    seen = {}

    def fn(x):
        seen["thread"] = threading.get_ident()
        return x + 1

    out = parallel_map(fn, [41])
    assert out == [42]
    assert seen["thread"] == calling_thread


def test_max_workers_one_runs_inline():
    calling_thread = threading.get_ident()
    seen = []

    def fn(x):
        seen.append(threading.get_ident())
        return x

    parallel_map(fn, [1, 2, 3], max_workers=1)
    assert all(t == calling_thread for t in seen)


def test_ordering_preserved_under_concurrency():
    # Later items finish first (reverse sleep) but output order must match input.
    def fn(x):
        time.sleep((5 - x) * 0.02)
        return x

    out = parallel_map(fn, [1, 2, 3, 4, 5])
    assert out == [1, 2, 3, 4, 5]


def test_parallel_run_ordering_preserved():
    def make(x):
        def t():
            time.sleep((5 - x) * 0.02)
            return x
        return t

    out = parallel_run([make(i) for i in range(1, 6)])
    assert out == [1, 2, 3, 4, 5]


def test_worker_exception_propagates_via_result():
    def fn(x):
        if x == 3:
            raise ValueError("boom on 3")
        return x

    with pytest.raises(ValueError, match="boom on 3"):
        parallel_map(fn, [1, 2, 3, 4])


def test_parallel_run_exception_propagates():
    def good():
        return 1

    def bad():
        raise RuntimeError("task failed")

    with pytest.raises(RuntimeError, match="task failed"):
        parallel_run([good, bad, good])
