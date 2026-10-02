from __future__ import annotations


class NextRunMaxIterationsReached(RuntimeError):
    def __init__(
        self,
        *,
        max_iterations: int,
        trigger_repr: str,
    ) -> None:
        super().__init__(
            "next_window exceeded max_iterations="
            f"{max_iterations} for trigger={trigger_repr}"
        )
        self.max_iterations = max_iterations
        self.trigger_repr = trigger_repr


class SyncJobNotAllowed(TypeError):
    """
    Raised by :class:`~schedium.asyncio.AsyncScheduler` when
    ``require_async_jobs=True`` and a job's callable is not known to be async.

    Parameters
    ----------
    job : object
        The offending job, kept on the exception as :attr:`job`.
    """

    def __init__(self, job: object) -> None:
        super().__init__(
            f"{job!r} does not wrap an async callable, but this AsyncScheduler was "
            "created with require_async_jobs=True. Use an `async def` function (or "
            "a callable object with an `async def __call__`), or create the "
            "scheduler with require_async_jobs=False to run it in a worker thread."
        )
        self.job = job
