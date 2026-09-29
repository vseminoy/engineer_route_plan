"""Owns the process pool `or_tools.solve_day` runs in, behind `plan_builder`'s watchdog.

`ProcessPoolExecutor(max_workers=1)` has no public way to abandon a worker that has
stopped answering: `Process.kill()` on it leaves the executor `BrokenProcessPool` for
every later submission. `restart` recreates the executor in its place, so a single
wedged `or_tools` build costs that one plan's build, not the process's ability to run
`or_tools` again until the app itself restarts.
"""

from concurrent.futures import Executor, ProcessPoolExecutor
from typing import Protocol

from src.logging import get_logger

logger = get_logger(__name__)


class SolverPool(Protocol):
    """What `PlanBuilder` needs of the pool — narrow enough that tests stand in a fake
    instead of a real `ProcessPoolExecutor`."""

    @property
    def executor(self) -> Executor: ...

    def restart(self) -> None: ...

    def shutdown(self, *, cancel_futures: bool = False) -> None: ...


class ProcessSolverPool:
    """The pool the running app uses. `max_workers=1`: only one OS process backs it, so
    `restart()` only ever has one future to worry about *if* `PlanBuilder` never submits
    a second `or_tools` build before the first one's future has been awaited — which is
    exactly what its own submission lock guarantees (see `plan_builder.py`'s `_solve`).
    Without that guarantee, a second, merely queued future would be cancelled by
    `restart()` along with the wedged one; this class does not defend against that on its
    own, because it has no way to know which futures are safe to drop.
    """

    def __init__(self, max_workers: int = 1) -> None:
        self._max_workers = max_workers
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

    @property
    def executor(self) -> Executor:
        return self._executor

    def restart(self) -> None:
        self._kill_workers()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = ProcessPoolExecutor(max_workers=self._max_workers)

    def shutdown(self, *, cancel_futures: bool = False) -> None:
        # Kills a busy worker exactly as `restart()` does: `ProcessPoolExecutor` has not
        # marked its workers as daemon processes since Python 3.9 (to allow a pool nested
        # inside another), so one left running past its parent's exit is reparented to
        # init and keeps running — for as long as its `or_tools` call does, unbounded if
        # that call is the very hang this watchdog exists to end. `wait=False` always: a
        # caller asking to exit fast (`app.py`'s `finally`, which must not outlive the
        # orchestrator's own shutdown grace period) would otherwise block on
        # `Executor.shutdown`'s default `wait=True` until the current solve finishes — up
        # to `SOLVER_TIME_LIMIT_S`, defeating the point of calling this at all instead of
        # just letting the process exit.
        self._kill_workers()
        self._executor.shutdown(wait=False, cancel_futures=cancel_futures)

    def _kill_workers(self) -> None:
        # `_processes` (the `multiprocessing.Process` objects backing the executor) is
        # not part of `ProcessPoolExecutor`'s public surface, but there is no other way
        # to end a worker that is already running a submitted call. A future Python
        # version could change or drop it; caught rather than left to blow up the one
        # code path that runs precisely when something has already gone wrong.
        try:
            processes = list(self._executor._processes.values())  # type: ignore[attr-defined]
        except AttributeError:
            # No worker is killed on this path: `restart()` still recreates the executor
            # (a fresh pool for the next build), and `shutdown()` still tells it not to
            # wait — the degradation is silent to the caller, so it must not be silent
            # here: whatever worker was running keeps running, unsupervised, until it
            # finishes on its own.
            logger.error("solver_pool_restart_missing_processes")
            return
        for process in processes:
            process.kill()
