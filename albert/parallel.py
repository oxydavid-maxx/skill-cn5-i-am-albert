"""Thread-pool helpers for parallelizing Claude/websearch calls across independent units.

`call_claude` and `websearch` are stateless and thread-safe (each call spawns its own
subprocess or requests session). Use these helpers for any loop where iterations do
not depend on each other — quadrant fan-outs, batched websearches, etc.
"""
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_MAX_WORKERS = 6


def parallel_map(fn: Callable[[T], R], items: Iterable[T], max_workers: int = DEFAULT_MAX_WORKERS) -> list[R]:
    """Map fn over items concurrently; preserve input ordering in output.

    Unlike executor.map which may buffer, this eagerly collects results.
    Exceptions from any worker propagate (first-encountered wins).
    """
    items_list = list(items)
    if not items_list:
        return []
    if len(items_list) == 1 or max_workers == 1:
        return [fn(x) for x in items_list]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items_list))) as ex:
        futures = [ex.submit(fn, x) for x in items_list]
        return [f.result() for f in futures]


def parallel_run(tasks: list[Callable[[], R]], max_workers: int = DEFAULT_MAX_WORKERS) -> list[R]:
    """Run zero-arg callables concurrently; preserve submission order."""
    if not tasks:
        return []
    if len(tasks) == 1 or max_workers == 1:
        return [t() for t in tasks]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as ex:
        futures = [ex.submit(t) for t in tasks]
        return [f.result() for f in futures]
