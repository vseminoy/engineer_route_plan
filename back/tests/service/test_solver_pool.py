import time
from concurrent.futures import ProcessPoolExecutor

import pytest

from src.service.solver_pool import ProcessSolverPool


def _sleep_forever() -> None:
    time.sleep(3600)


def _trivial() -> int:
    return 42


def test_restart_survives_a_killed_worker() -> None:
    pool = ProcessSolverPool(max_workers=1)
    future = pool.executor.submit(_sleep_forever)
    time.sleep(0.2)  # let the worker actually start the sleep before killing it

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


def test_process_solver_pool_is_a_process_pool_executor_underneath() -> None:
    pool = ProcessSolverPool(max_workers=1)
    try:
        assert isinstance(pool.executor, ProcessPoolExecutor)
    finally:
        pool.shutdown()
