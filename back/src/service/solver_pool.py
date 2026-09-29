"""Owns the process pool `or_tools.solve_day` runs in, behind `plan_builder`'s watchdog.

`ProcessPoolExecutor(max_workers=1)` has no public way to abandon a worker that has
stopped answering: `Process.kill()` on it leaves the executor `BrokenProcessPool` for
every later submission. `restart` recreates the executor in its place, so a single
wedged `or_tools` build costs that one plan's build, not the process's ability to run
`or_tools` again until the app itself restarts.
"""

from concurrent.futures import Executor, ProcessPoolExecutor
from typing import Protocol


class SolverPool(Protocol):
    """What `PlanBuilder` needs of the pool — narrow enough that tests stand in a fake
    instead of a real `ProcessPoolExecutor`."""

    @property
    def executor(self) -> Executor: ...

    def restart(self) -> None: ...

    def shutdown(self, *, cancel_futures: bool = False) -> None: ...


class ProcessSolverPool:
    """The pool the running app uses. `max_workers=1`: `or_tools` never runs two builds
    at once, a second concurrent request queues behind the first (see `plan_builder.py`).
    """

    def __init__(self, max_workers: int = 1) -> None:
        self._max_workers = max_workers
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

    @property
    def executor(self) -> Executor:
        return self._executor

    def restart(self) -> None:
        # `_processes` (the `multiprocessing.Process` objects backing the executor) is
        # not part of `ProcessPoolExecutor`'s public surface, but there is no other way
        # to end a worker that is already running a submitted call.
        for process in self._executor._processes.values():  # type: ignore[attr-defined]
            process.kill()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = ProcessPoolExecutor(max_workers=self._max_workers)

    def shutdown(self, *, cancel_futures: bool = False) -> None:
        self._executor.shutdown(cancel_futures=cancel_futures)
