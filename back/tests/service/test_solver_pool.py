import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pytest

from src.service.solver_pool import ProcessSolverPool


def _signal_then_sleep_forever(started: Any) -> None:
    started.set()
    time.sleep(3600)


def _trivial() -> int:
    return 42


def test_restart_survives_a_killed_worker() -> None:
    """`started` (set by the worker itself, the moment it begins running) replaces a
    fixed `time.sleep` before `restart()`: a flat delay would either wait longer than
    necessary or, on a slow runner, kill the worker before it has actually started the
    long call — proving the easier case of killing a process that never began the work
    this test is meant to interrupt. A plain `multiprocessing.Event()` cannot be passed
    through `ProcessPoolExecutor.submit`'s call queue (it is picklable only through
    process inheritance, not through an arbitrary pickle) — `Manager().Event()` returns a
    proxy that is."""
    pool = ProcessSolverPool(max_workers=1)
    with multiprocessing.Manager() as manager:
        started = manager.Event()
        future = pool.executor.submit(_signal_then_sleep_forever, started)
        assert started.wait(timeout=10), "worker did not start in time"

        pool.restart()

        assert not future.done()
        assert pool.executor.submit(_trivial).result(timeout=10) == 42
    pool.shutdown()


def test_restart_replaces_the_executor_instance() -> None:
    pool = ProcessSolverPool(max_workers=1)
    original = pool.executor

    pool.restart()

    assert pool.executor is not original
    pool.shutdown()


def test_shutdown_stops_accepting_new_work() -> None:
    pool = ProcessSolverPool(max_workers=1)

    pool.shutdown()

    with pytest.raises(RuntimeError):
        pool.executor.submit(_trivial)


def test_shutdown_does_not_wait_for_a_busy_worker() -> None:
    """`Executor.shutdown` defaults to `wait=True`; `ProcessSolverPool.shutdown` must
    override that default, or `app.py`'s `finally` — which must exit fast, within the
    orchestrator's own grace period, not try to outlast a wedged or merely slow solve —
    would block on it until the running call finishes."""
    pool = ProcessSolverPool(max_workers=1)
    with multiprocessing.Manager() as manager:
        started = manager.Event()
        pool.executor.submit(_signal_then_sleep_forever, started)
        assert started.wait(timeout=10), "worker did not start in time"

        started_at = time.monotonic()
        pool.shutdown(cancel_futures=True)
        elapsed = time.monotonic() - started_at

        assert elapsed < 5, f"shutdown() waited {elapsed:.1f}s for a worker sleeping 3600s"


def test_shutdown_kills_a_busy_worker() -> None:
    """Without this, a worker mid-`or_tools`-call is not a daemon process
    (`ProcessPoolExecutor` stopped marking them as such in Python 3.9) and would outlive
    `shutdown()` — reparented to init on the host, running unsupervised for as long as its
    call does, unbounded if that call is exactly the hang the watchdog exists to end."""
    pool = ProcessSolverPool(max_workers=1)
    with multiprocessing.Manager() as manager:
        started = manager.Event()
        pool.executor.submit(_signal_then_sleep_forever, started)
        assert started.wait(timeout=10), "worker did not start in time"
        process = next(iter(pool.executor._processes.values()))  # type: ignore[attr-defined]

        pool.shutdown(cancel_futures=True)

        process.join(timeout=5)
        assert not process.is_alive(), f"worker pid {process.pid} still alive after shutdown()"


def test_process_solver_pool_is_a_process_pool_executor_underneath() -> None:
    pool = ProcessSolverPool(max_workers=1)
    try:
        assert isinstance(pool.executor, ProcessPoolExecutor)
    finally:
        pool.shutdown()
